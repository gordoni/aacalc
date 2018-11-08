#!/usr/bin/env python3

# AIPlanner - Deep Learning Financial Planner
# Copyright (C) 2018 Gordon Irlam
#
# All rights reserved. This program may not be used, copied, modified,
# or redistributed without permission.
#
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.

from csv import writer
from json import dumps
from os import chmod, environ, mkdir
from subprocess import run

import tensorflow as tf

from baselines.common import (
    tf_util as U,
)
from baselines.common.misc_util import set_global_seeds

from gym_fin.common.cmd_util import arg_parser, fin_arg_parse, make_fin_env
from gym_fin.common.evaluator import Evaluator

def eval_model(eval_model_params, *, eval_seed, eval_num_timesteps, eval_render, model_dir, result_dir, num_trace_episodes, num_environments, pdf_buckets):

    try:
        mkdir(result_dir)
    except FileExistsError:
        pass

    prefix = result_dir + '/aiplanner'

    try:

        eval_seed += 1000000 # Use a different seed than might have been used during training.
        set_global_seeds(eval_seed)
        envs = []
        for _ in range(num_environments):
            envs.append(make_fin_env(**eval_model_params, action_space_unbounded = True, direct_action = False))
            eval_model_params['display_returns'] = False # Only have at most one env display returns.
        obs = envs[0].reset()

        with U.make_session(num_cpu=1) as session:

            tf.saved_model.loader.load(session, [tf.saved_model.tag_constants.SERVING], model_dir)
            g = tf.get_default_graph()
            observation_tf = g.get_tensor_by_name('pi/ob:0')
            action_tf = g.get_tensor_by_name('pi/action:0')
            action, = session.run(action_tf, feed_dict = {observation_tf: [obs]})
            interp = envs[0].unwrapped.interpret_action(action)

            interp['asset_allocation'] = interp['asset_allocation'].as_list()
            interp_str = dumps(interp)
            with open(result_dir + '/aiplanner-initial.json', 'w') as w:
                 w.write(interp_str)

            evaluator = Evaluator(envs, eval_seed, eval_num_timesteps, render = eval_render, num_trace_episodes = num_trace_episodes, pdf_buckets = pdf_buckets)

            def pi(obss):
                action = session.run(action_tf, feed_dict = {observation_tf: obss})
                return action

            ce, ce_stderr, low, high = evaluator.evaluate(pi)

            plot(prefix, evaluator.trace, evaluator.consume_pdf)

            final_data = {
                'error': None,
                'ce': ce,
                'ce_stderr': ce_stderr,
                'ce_low': low,
                'ce_high': high,
                'consume_preretirement': envs[0].unwrapped.params.consume_preretirement,
                'preretirement_ppf': evaluator.preretirement_ppf,
            }
            exception = None

    except Exception as e:
        exception = e
        error_msg = str(e)
        if not error_msg:
            error_msg = e.__class__.__name__ + ' exception encountered.'
        final_data = {
            'error': error_msg,
        }

    final_str = dumps(final_data)
    with open(prefix + '-final.json', 'w') as w:
        w.write(final_str)

    if exception:
        raise exception

def plot(prefix, traces, consume_pdf):

    with open(prefix + '-trace.csv', 'w') as f:
        csv_writer = writer(f)
        for trace in traces:
            for i, step in enumerate(trace):
                couple_plot = step['alive_count'] == 2
                single_plot = step['alive_count'] == 1
                try:
                    if step['alive_count'] == 2 and trace[i + 1]['alive_count'] == 1:
                        single_plot = True
                except KeyError:
                    pass
                csv_writer.writerow((step['age'], int(couple_plot), int(single_plot), step['gi_sum'], step['p_sum'], step['consume']))
            csv_writer.writerow(())

    with open(prefix + '-consume-pdf.csv', 'w') as f:
        csv_writer = writer(f)
        csv_writer.writerows(consume_pdf)

    environ['AIPLANNER_FILE_PREFIX'] = prefix
    run(['./plot.gnuplot'], check = True)

def main():
    global args

    parser = arg_parser()
    parser.add_argument('--result-dir', default = './')
    parser.add_argument('--num-trace-episodes', type = int, default = 5)
    parser.add_argument('--num-environments', type = int, default = 10) # Number of parallel environments to use for a single model. Speeds up tensor flow.
    parser.add_argument('--pdf-buckets', type = int, default = 20) # Number of non de minus buckets to use in computing consume probability density distribution.
    training_model_params, eval_model_params, args = fin_arg_parse(parser, training = False, dump = False)

    eval_model(eval_model_params, **args)

if __name__ == '__main__':
    main()