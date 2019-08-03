#!/usr/bin/env python3

# AIPlanner - Deep Learning Financial Planner
# Copyright (C) 2019 Gordon Irlam
#
# All rights reserved. This program may not be used, copied, modified,
# or redistributed without permission.
#
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.

from glob import glob
from os import getpriority, mkdir, PRIO_PROCESS, setpriority
from os.path import abspath
from shutil import rmtree

from baselines.common import boolean_flag
#from baselines.common.misc_util import set_global_seeds

import ray
from ray.tune import run_experiments, function
from ray.tune.config_parser import make_parser

from gym_fin.common.cmd_util import arg_parser, fin_arg_parse
from gym_fin.envs.model_params import dump_params_file
from gym_fin.envs.fin_env import FinEnv

class RayFinEnv(FinEnv):

    def __init__(self, config):
        super().__init__(**config)

def train(training_model_params, *, redis_address, train_anneal_num_timesteps, train_seeds,
    train_batch_size, train_minibatch_size, train_optimizer_epochs, train_optimizer_step_size, train_entropy_coefficient,
    train_save_frequency, train_max_failures, train_resume,
    train_num_timesteps, train_single_num_timesteps, train_couple_num_timesteps,
    train_seed, nice, num_cpu, model_dir, **ray_kwargs):

    priority = getpriority(PRIO_PROCESS, 0)
    priority += nice
    setpriority(PRIO_PROCESS, 0, priority)

    while model_dir and model_dir[-1] == '/':
        model_dir = model_dir[:-1]
    assert model_dir.endswith('.tf')
    try:
        if not train_resume:
            rmtree(model_dir)
    except FileNotFoundError:
        pass

    #set_global_seeds(train_seed)
        # Training is currently non-deterministic.
        # Would probably need to call rllib.utils.seed.seed() from rllib.agents.agent.__init__() with a triply repeated config["seed"] parameter to fix.

    training_model_params['action_space_unbounded'] = True
    training_model_params['observation_space_ignores_range'] = True

    try:
        mkdir(model_dir)
    except FileExistsError:
        pass
    dump_params_file(model_dir + '/params.txt', training_model_params)

    ray.init(redis_address=redis_address)
    #ray.init(object_store_memory=int(2e9))

    algorithm = training_model_params['algorithm']

    lr_schedule = [
        (0, train_optimizer_step_size),
        (max(0, train_num_timesteps - train_anneal_num_timesteps), train_optimizer_step_size),
    ]
    # Exponentially decaying anneal phase. Not usually needed; at least not when entropy_coeff provide regularization.
    #     Consider estimating the non-representativeness of the batch brought about by it being a sample from a larger universe.
    #     4 samples would have a stderr of 1/2 the non-representativeness.
    #     Thus every 4 batches would cut down the non-representativeness remaining to be cut down by a factor of 2.
    while lr_schedule[-1][0] < train_num_timesteps:
        lr_schedule.append((lr_schedule[-1][0] + train_batch_size, lr_schedule[-1][1] / 2 ** (1/4)))
    agent_config = {

        'A2C': {
        },

        'A3C': {
        },

        'PG': {
        },

        'DDPG': {
        },

        # APPO currently doesn't support action space Box. Hence currently not useful.
        'APPO': {
            'train_batch_size': 500,
            'lr_schedule': lr_schedule,
        },

        'PPO': {
            'model': {
                # Changing the fully connected net size from 256x256 (the default) to 128x128 doesn't appear to appreciably alter CE values.
                # At least not when the only actions are consumption and stock allocation with 4m timesteps.
                # Keep at 256x256 in case need more net capacity for duration and SPIA decisions, or beyond 4m timesteps.
                # Reducing size is unlikely to improve the run time performance as it is dominated by fixed overhead costs:
                #     runner.run(obss, policy_graph = runner.local_policy_graph):
                #         256x256 (r5.large): 1.1ms + 0.013ms x num_observations_in_batch
                #         128x128 (r5.large): 1.1ms + 0.009ms x num_observations_in_batch
                #'fcnet_hiddens': (128, 128),
            },
            'train_batch_size': train_batch_size,
            'sgd_minibatch_size': train_minibatch_size,
            'num_sgd_iter': train_optimizer_epochs,
            'entropy_coeff': train_entropy_coefficient,
            'vf_clip_param': 10.0, # Currently equal to PPO default value.
                # Clip value function advantage estimates. We expect most rewards to be roughly in [-1, 1],
                # so if we get something far from this we don't want to train too hard on it.
            'kl_target': 1, # Disable PPO KL-Penalty, use PPO Clip only; gives better CE.
            'lr_schedule': lr_schedule,
        },

        'PPO.baselines': { # Compatible with AIPlanner's OpenAI baselines ppo1 implementation.
            'model': {
                'fcnet_hiddens': (64, 64),
            },
            'lambda': 0.95,
            'sample_batch_size': 256,
            'train_batch_size': 4096,
            #'sgd_minibatch_size': 128,
            'num_sgd_iter': 10,
            'lr_schedule': (
                (0, 3e-4),
                (train_num_timesteps, 0)
            ),
            'clip_param': 0.2,
            'vf_clip_param': float('inf'),
            'kl_target': 1,
            'batch_mode': 'complete_episodes',
            #'observation_filter': 'NoFilter',
        },

    }[algorithm]
    agent_config = dict(agent_config, **ray_kwargs['config'])

    run = algorithm[:-len('.baselines')] if algorithm.endswith('.baselines') else algorithm
    checkpoint_freq = max(1, train_save_frequency // agent_config['train_batch_size']) if train_save_frequency != None else 0

    run_experiments(
        {
            'seed_' + str(seed): {

                'run': run,

                'config': dict({
                    'env': RayFinEnv,
                    'env_config': training_model_params,
                    'clip_actions': False,
                    'gamma': 1,

                    #'num_gpus': 0,
                    #'num_cpus_for_driver': 1,
                    'num_workers': 1 if algorithm in ('A3C', 'APPO') else 0,
                    #'num_envs_per_worker': 1,
                    #'num_cpus_per_worker': 1,
                    #'num_gpus_per_worker': 0,

                    'tf_session_args': {
                        'intra_op_parallelism_threads': num_cpu,
                        'inter_op_parallelism_threads': num_cpu,
                    },
                    'local_evaluator_tf_session_args': {
                        'intra_op_parallelism_threads': num_cpu,
                        'inter_op_parallelism_threads': num_cpu,
                    }
                }, **agent_config),

                'stop': {
                    'timesteps_total': train_num_timesteps,
                },

                'local_dir': abspath(model_dir),
                'checkpoint_freq': checkpoint_freq,
                'checkpoint_at_end': True,
                'max_failures': train_max_failures,
            } for seed in range(train_seed, train_seed + train_seeds)
        },
        resume = train_resume,
        queue_trials = redis_address != None
    )

def main():
    parser = make_parser(lambda: arg_parser(evaluate=False))
    parser.add_argument('--redis-address')
    # --train-num-timesteps:
        # Increased mean CE levels are likely for a large number of timesteps, but it is a case of diminishing returns.
        # Eg. for a gamma of 6 and a large portfolio, going from 2m to 4m increases the CE by 1.1%, but going to 6m only increases it by a further 0.5%.
    parser.add_argument('--train-anneal-num-timesteps', type=int, default=0)
    parser.add_argument('--train-seeds', type=int, default=1) # Number of parallel seeds to train.
    parser.add_argument('--train-batch-size', type=int, default=200000)
        # PPO default batch size is 4000. For a gamma of 6 and a large portfolio it results in asset allocation heavily biased in favor of stocks, and a poor mean CE.
        # The poor CE is probably the result of each batch being non-representative of the overall situation given the stochastic nature of the problem.
        # Inceasing value too 50000 or more improves performance and reduces the asset allocation bias, but never eliminates it.
        # It would appear the larger the batch size the higher the mean CE, but also the larger the number of timesteps it takes to reach that CE level.
        # A value of 100000 appears best for 3m to 7m timesteps with a 5e-5 step size.
        # 200000 is probably marginally better than 100000 for 50m timesteps for a 5e-6 step size.
    parser.add_argument('--train-minibatch-size', type=int, default=128)
    parser.add_argument('--train-optimizer-epochs', type=int, default=30)
    parser.add_argument('--train-optimizer-step-size', type=float, default=5e-6)
        # PPO default is 5e-5. Trains rapidly, but training curve ends up having a lot of CE variability over timesteps.
    parser.add_argument('--train-entropy-coefficient', type=float, default=0)
        # Value might be critical to getting optimal performance.
        # Value to use probably depends on the complexity of the scenario.
        # A value of 1e-3 reduced CE stdev and increased CE mean for a 256x256 tf model on a Merton like model with stochastic life expectancy and guaranteed income.
    parser.add_argument('--train-save-frequency', type=int, default=None)
    parser.add_argument('--train-max-failures', type=int, default=3)
    boolean_flag(parser, 'train-resume', default = False) # Resume training rather than starting new trials.
        # To resume running trials for which Ray appears to have hung with no running worker processes or worker nodes (check has redis died?),
        # it is recommended first make a copy the model(s) directory, and then stop Ray and reinvoke training with --train-resume.
        # First time attempted this got redis connection error on 2 of 20 processes, which couldn't be corrected,
        # but having a copy of the model(s) directory allowed me to rollback and retry successfully.
        #
        # To attempt to resume trials that have errored edit the latest <model_dir>/seed_0/experiment_state-<date>.json (Note: Use seed_0 for all experiments).
        # changing all of their statuses from "ERROR" to "RUNNING", and then invoke this script with --train-resume.
        # Didn't work, state changed to "RUNNING", but not actually running.
        #
        # To attempt to extend already completed trials edit the latest <model_dir>/seed_0/experiment_state-<date>.json
        # changing all of their statuses from "TERMINATED" to "RUNNING", and timeteps_total to <new_timestep_limit>,
        # then invoke this script with --train-resume --train-num-timesteps=<new_timestep_limit>.
        # Didn't work, not sure what the problem is, but Rllib resume is currently experimental.
    training_model_params, _, args = fin_arg_parse(parser, evaluate=False)
    if not training_model_params['algorithm']:
         training_model_params['algorithm'] = 'PPO'
    train(training_model_params, **args)

if __name__ == '__main__':
    main()
