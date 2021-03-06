# AIPlanner - Deep Learning Financial Planner
# Copyright (C) 2018-2021 Gordon Irlam
#
# All rights reserved. This program may not be used, copied, modified,
# or redistributed without permission.
#
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.

from glob import glob
from os.path import isdir, join
from pickle import load
from shutil import rmtree

import numpy as np

from ai.common.ray_util import RayFinEnv

class TFRunner:

    def __init__(self, *, train_dirs = ['aiplanner.tf'], allow_tensorflow = True, checkpoint_name = None, eval_model_params, couple_net = True,
        address = None, num_workers = 0, runner_seed = 0, num_environments = 1, num_cpu = None,
        evaluator = True, export_model = False):

        self.couple_net = couple_net
        self.session = None
        self.local_policy_graph = None
        self.remote_evaluators = None
        self.sessions = []
        self.observation_tfs = []
        self.action_tfs = []

        tf_name = checkpoint_name or 'tensorflow'
        tf_dir = train_dirs[0] + '/' + tf_name
        tensorflow = isdir(tf_dir)
        #rllib_checkpoints = glob(train_dirs[0] + '/*/checkpoint_*')
        if not allow_tensorflow or not tensorflow or export_model:

            # Rllib.
            import ray
            from ray.rllib.agents.registry import get_agent_class
            from ray.rllib.evaluation.worker_set import WorkerSet

            if not ray.is_initialized():
                ray.init(address = address, include_dashboard = False)

            weights = []
            first = True
            for train_dir in train_dirs:

                checkpoints = glob(train_dir + '**/checkpoint_*', recursive = True)
                if checkpoint_name:
                    checkpoint_nm = checkpoint_name
                else:
                    assert checkpoints, 'No Rllib checkpoints found: ' + train_dir
                    checkpoint_nm = 'checkpoint_' + str(max(int(checkpoint.split('_')[-1]) for checkpoint in checkpoints))
                checkpoint_dir, = glob(train_dir + '**/' + checkpoint_nm, recursive = True)
                checkpoint, = glob(checkpoint_dir + '/checkpoint-*[0-9]')

                if first:
                    config_path = join(checkpoint_dir, '../params.pkl')
                    with open(config_path, 'rb') as f:
                        config = load(f)

                    cls = get_agent_class(config['env_config']['algorithm'])
                    config['env_config'] = eval_model_params
                    config['num_workers'] = 0 # So don't run out of actors doing checkpoint restore.
                    config['num_envs_per_worker'] = num_environments
                    config['local_tf_session_args'] = {
                        'intra_op_parallelism_threads': num_cpu,
                        'inter_op_parallelism_threads': num_cpu,
                    }
                    config['seed'] = runner_seed * 1000 # Workers are assigned consecutive seeds.

                agent = cls(env = RayFinEnv, config = config)
                agent.restore(checkpoint)

                if export_model:

                    export_dir = train_dir + '/tensorflow'
                    assert '.tf/' in export_dir
                    try:
                        rmtree(export_dir)
                    except FileNotFoundError:
                        pass

                    # export_policy_model() is a nop in Ray 0.8.5 for eager tf (TensorFlow 2).
                    agent.export_policy_model(export_dir)

                if not evaluator:
                    return

                weight = agent.get_weights()['default_policy']
                weights.append(weight)

                first = False

            framework = config.get('framework')

            if framework == 'tfe':
                base_policy_class = agent._policy_class.as_eager() # Change to agent.get_policy().__class__.as_eager()?
            else:
                base_policy_class = agent.get_policy().__class__

            class EnsemblePolicy(base_policy_class):

                def __init__(self, observation_space, action_space, config, *args, **kwargs):

                    self.policies = []
                    for w in weights:
                        if framework == 'tfe':
                            import tensorflow as tf # Must do after agent.restore() if not eager.
                            graph = tf.Graph()
                            with graph.as_default() as g:
                                tf_config = tf.compat.v1.ConfigProto(
                                    inter_op_parallelism_threads = num_cpu,
                                    intra_op_parallelism_threads = num_cpu
                                )
                                with tf.compat.v1.Session(graph = graph, config = tf_config).as_default() as sess:
                                    policy = base_policy_class(observation_space, action_space, config, *args, **kwargs)
                        else:
                            policy = base_policy_class(observation_space, action_space, config, *args, **kwargs)
                        self.policies.append(policy)
                    super().__init__(observation_space, action_space, config, *args, **kwargs)

                def set_weights(self, weights):

                    for policy, w in zip(self.policies, weights):
                        policy.set_weights(w)

                def compute_actions(self, obs_batch, state_batches = [], prev_action_batch = [], prev_reward_batch = [], *args, **kwargs):

                    actions_ca = [policy.compute_actions(obs_batch, state_batches, prev_action_batch, prev_reward_batch,
                                                         *args, **dict(kwargs, explore = False)) for policy in self.policies]
                    actions = np.array([action[0] for action in actions_ca])
                    # Get slightly better CEs (retired, SPIAs, gamma=1.5) taking mean, than first dropping high/low.
                    #mean_action = (np.sum(actions, axis = 0) - np.amin(actions, axis = 0) - np.amax(actions, axis = 0)) / (actions.shape[0] - 2)
                    mean_action = np.mean(actions, axis = 0)
                    return [mean_action] + list(actions_ca[0][1:])

            if framework == 'tfe':

                class EnsemblePolicy_eager(agent._policy_class): # Change to agent.get_policy().__class__?

                    def as_eager():

                        return EnsemblePolicy

                policy_class = EnsemblePolicy_eager

            else:

                policy_class = EnsemblePolicy

            agent_weights = {'default_policy': weights}

            env_creator = lambda x: RayFinEnv(config['env_config'])
            # Delete workers and optimizer, they cause deserialization to fail.
            # Not precisely sure why, but this fixes the problem. They aren't needed for remote evaluation.
            #del agent.workers
            #del agent.optimizer
            workers = WorkerSet(env_creator = env_creator, policy_class = policy_class, trainer_config = agent.config, num_workers = num_workers)
            workers.foreach_worker(lambda w: w.set_weights(agent_weights))
            self.remote_evaluators = workers.remote_workers()

            self.policy = workers.local_worker().get_policy()

        else:

            import tensorflow as tf

            tf_config = tf.ConfigProto(
                inter_op_parallelism_threads = num_cpu,
                intra_op_parallelism_threads = num_cpu
            )

            try:

                # Rllib tensorflow.
                for train_dir in train_dirs:
                    tf_dir = train_dir + '/' + tf_name
                    graph = tf.Graph()
                    with graph.as_default() as g:
                        with tf.Session(graph = graph, config = tf_config).as_default() as session:
                            metagraph = tf.saved_model.loader.load(session, [tf.saved_model.tag_constants.SERVING], tf_dir)
                            inputs = metagraph.signature_def['serving_default'].inputs
                            outputs = metagraph.signature_def['serving_default'].outputs
                            observation_tf = graph.get_tensor_by_name(inputs['observations'].name)
                            action_tf = graph.get_tensor_by_name(outputs['actions'].name)
                            self.sessions.append(session)
                            self.observation_tfs.append(observation_tf)
                            self.action_tfs.append(action_tf)

            except KeyError:

                self.session = tf.Session(config = tf_config).__enter__()

                try:

                    # OpenAI Spinning Up.
                    from spinup.utils.logx import restore_tf_graph
                    model_graph = restore_tf_graph(self.session, tf_dir + '/simple_save')
                    self.observation_sigle_tf = observation_couple_tf = model_graph['x']
                    try:
                        self.action_single_tf = action_couple_tf = model_graph['mu']
                    except KeyError:
                        self.action_single_tf = action_couple_tf = model_graph['pi']

                except (ModuleNotFoundError, IOError):

                    # OpenAI Baselines.
                    tf.saved_model.loader.load(self.session, [tf.saved_model.tag_constants.SERVING], tf_dir)
                    g = tf.get_default_graph()
                    self.observation_single_tf = g.get_tensor_by_name('single/ob:0')
                    self.action_single_tf = g.get_tensor_by_name('single/action:0')
                    try:
                        self.observation_couple_tf = g.get_tensor_by_name('couple/ob:0')
                        self.action_couple_tf = g.get_tensor_by_name('couple/action:0')
                    except KeyError:
                        self.observation_couple_tf = self.action_couple_tf = None

    def __enter__(self):

        return self

    def __exit__(self, exception_type, exception_value, traceback):

        if self.session:
            self.session.__exit__(exception_type, exception_value, traceback)
            tf.reset_default_graph()

    def is_couple(self, ob):
        return ob[0] == 1

    def _run_unit(self, couple, obss):

        if self.sessions:

                actions = [session.run(action_tf, feed_dict = {observation_tf: obss}) \
                    for session, observation_tf, action_tf in zip(self.sessions, self.observation_tfs, self.action_tfs)]
                mean_action = np.mean(actions, axis = 0)
                return mean_action

        if self.session:

            action_tf = self.action_couple_tf if couple else self.action_single_tf
            observation_tf = self.observation_couple_tf if couple else self.observation_single_tf
            return self.session.run(action_tf, feed_dict = {observation_tf: obss})

        else:

            return self.policy.compute_actions(obss)[0]

    def run(self, obss):

        if self.couple_net:

            single_obss = []
            couple_obss = []
            single_idx = []
            couple_idx = []
            for i, obs in enumerate(obss):
                if self.is_couple(obs) and self.couple_net:
                    couple_obss.append(obs)
                    couple_idx.append(i)
                else:
                    single_obss.append(obs)
                    single_idx.append(i)
            action = [None] * len(obss)
            if single_obss:
                single_action = self._run_unit(False, single_obss)
                for i, act in zip(single_idx, single_action):
                    action[i] = act
            if couple_obss:
                couple_action = self._run_unit(True, couple_obss)
                for i, act in zip(couple_idx, couple_action):
                    action[i] = act

        else:

            action = self._run_unit(False, obss)

        return action
