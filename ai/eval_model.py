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
from math import ceil, exp, sqrt
from os import chmod, environ, getpriority, mkdir, PRIO_PROCESS, setpriority
from subprocess import run

import tensorflow as tf

from baselines.common import (
    tf_util as U,
    boolean_flag,
)
from baselines.common.misc_util import set_global_seeds

from gym_fin.envs.asset_allocation import AssetAllocation
from gym_fin.envs.policies import policy
from gym_fin.common.cmd_util import arg_parser, fin_arg_parse, make_fin_env
from gym_fin.common.evaluator import Evaluator

from spinup.utils.logx import restore_tf_graph

from gym_fin.envs.model_params import load_params_file

def pi_merton(env, obs, continuous_time = False):
    observation = env.decode_observation(obs)
    assert observation['life_expectancy_both'] == 0
    life_expectancy = observation['life_expectancy_one']
    gamma = env.params.gamma_low
    mu = env.stocks.mu
    sigma = env.stocks.sigma
    r = env.bills.mu
    alpha = mu + sigma ** 2 / 2
    stocks_allocation = (alpha - r) / (sigma ** 2 * gamma)
    nu = ((gamma - 1) / gamma) * ((alpha - r) * stocks_allocation / 2 + r)
    if nu == 0:
        consume_fraction = 1 / life_expectancy
    elif continuous_time:
        # Merton.
        consume_fraction = nu / (1 - exp(- nu * life_expectancy))
    else:
        # Samuelson.
        a = exp(nu * env.params.time_period)
        t = ceil(life_expectancy / env.params.time_period) - 1
        consume_fraction = a ** t * (a - 1) / (a ** (t + 1) - 1) / env.params.time_period
    return consume_fraction, stocks_allocation

def is_couple(ob):
    return ob[0] == 1

def eval_model(eval_model_params, *, merton, samuelson, annuitize, eval_couple_net, eval_seed, eval_num_timesteps, eval_render, nice, num_cpu, model_dir, \
    search_consume_initial_around, result_dir, num_trace_episodes, num_environments, pdf_buckets):

    try:
        mkdir(result_dir)
    except FileExistsError:
        pass

    prefix = result_dir + '/aiplanner'

    try:

        priority = getpriority(PRIO_PROCESS, 0)
        priority += nice
        setpriority(PRIO_PROCESS, 0, priority)

        assert sum((model_dir != 'aiplanner.tf', merton, samuelson, annuitize)) <= 1
        model = not (merton or samuelson or annuitize)

        eval_seed += 1000000 # Use a different seed than might have been used during training.
        set_global_seeds(eval_seed)

        if model:
            assets_dir = model_dir + '/assets.extra'
            train_model_params = load_params_file(assets_dir + '/params.txt')
            eval_model_params['action_space_unbounded'] = train_model_params['action_space_unbounded']
            eval_model_params['observation_space_ignores_range'] = train_model_params['observation_space_ignores_range']
        else:
            eval_model_params['action_space_unbounded'] = True
            eval_model_params['observation_space_ignores_range'] = False

        envs = []
        for _ in range(num_environments):
            envs.append(make_fin_env(**eval_model_params, direct_action = not model))
            eval_model_params['display_returns'] = False # Only have at most one env display returns.
        env = envs[0].unwrapped

        if env.params.consume_policy != 'rl' and env.params.annuitization_policy != 'rl' and env.params.asset_allocation_policy != 'rl' and \
            (not env.params.real_bonds or env.params.real_bonds_duration != None) and \
            (not env.params.nominal_bonds or env.params.nominal_bonds_duration != None):
            model = False

        obs = env.reset()

        if merton or samuelson:

            consume_fraction, stocks_allocation = pi_merton(env, obs, continuous_time = merton)
            asset_allocation = AssetAllocation(stocks = stocks_allocation, bills = 1 - stocks_allocation)
            interp = env.interpret_spending(consume_fraction, asset_allocation)

        elif annuitize:

            consume_initial = env.gi_sum() + env.p_sum() / (env.params.time_period + env.real_spia.premium(1, mwr = env.params.real_spias_mwr))
            consume_fraction_initial = consume_initial / env.p_plus_income()
            asset_allocation = AssetAllocation(stocks = 1)
            interp = env.interpret_spending(consume_fraction_initial, asset_allocation, real_spias_fraction = 1)

        else:

            session = U.make_session(num_cpu = num_cpu).__enter__()
            try:
                model_graph = restore_tf_graph(session, model_dir + '/simple_save')
                observation_sigle_tf = observation_couple_tf = model_graph['x']
                try:
                    action_single_tf = action_couple_tf = model_graph['mu']
                except KeyError:
                    action_single_tf = action_couple_tf = model_graph['pi']
            except IOError:
                tf.saved_model.loader.load(session, [tf.saved_model.tag_constants.SERVING], model_dir)
                g = tf.get_default_graph()
                observation_single_tf = g.get_tensor_by_name('single/ob:0')
                action_single_tf = g.get_tensor_by_name('single/action:0')
                try:
                    observation_couple_tf = g.get_tensor_by_name('couple/ob:0')
                    action_couple_tf = g.get_tensor_by_name('couple/action:0')
                except KeyError:
                    observation_couple_tf = action_couple_tf = None
                #v_tf = g.get_tensor_by_name('single/pi/v:0')

            def run_tf(obss):
                single_obss = []
                couple_obss = []
                single_idx = []
                couple_idx = []
                for i, obs in enumerate(obss):
                    if is_couple(obs) and eval_couple_net:
                        couple_obss.append(obs)
                        couple_idx.append(i)
                    else:
                        single_obss.append(obs)
                        single_idx.append(i)
                action = [None] * len(obss)
                if single_obss:
                    single_action = session.run(action_single_tf, feed_dict = {observation_single_tf: single_obss})
                    for i, act in zip(single_idx, single_action):
                        action[i] = act
                if couple_obss:
                    couple_action = session.run(action_couple_tf, feed_dict = {observation_couple_tf: couple_obss})
                    for i, act in zip(couple_idx, couple_action):
                        action[i] = act
                return action

            action, = run_tf([obs])
            interp = env.interpret_action(action)

        interp['asset_classes'] = interp['asset_allocation'].classes()
        interp['asset_allocation'] = interp['asset_allocation'].as_list()
        interp['name'] = env.params.name
        interp_str = dumps(interp)
        with open(result_dir + '/aiplanner-initial.json', 'w') as w:
            w.write(interp_str)

        print()
        print('Initial properties for first episode:')
        print('    Consume:', interp['consume'])
        print('    Asset allocation:', interp['asset_allocation'])
        print('    401(k)/IRA contribution:', interp['retirement_contribution'])
        print('    Real income annuities purchase:', interp['real_spias_purchase'])
        print('    Nominal income annuities purchase:', interp['nominal_spias_purchase'])
        print('    Real bonds duration:', interp['real_bonds_duration'])
        print('    Nominal bonds duration:', interp['nominal_bonds_duration'])

        # if model:

        #     v, = session.run(v_tf, feed_dict = {observation_tf: [obs]})
        #     print('    Predicted certainty equivalent: ', env.utility.inverse(v / env.alive_years))
        #         # Only valid if train and eval have identical age_start and life table.
        #         # Otherwise need to simulate to determine CE; this also provides percentile ranges.

        print()

        evaluator = Evaluator(envs, eval_seed, eval_num_timesteps, render = eval_render, num_trace_episodes = num_trace_episodes, pdf_buckets = pdf_buckets)

        def pi(obss):

            if model:

                action = run_tf(obss)
                return action

            elif merton or samuelson:

                results = []
                for obs in obss:
                    consume_fraction, stocks_allocation = pi_merton(env, obs, continuous_time = merton)
                    observation = env.decode_observation(obs)
                    assert observation['life_expectancy_both'] == 0
                    life_expectancy = observation['life_expectancy_one']
                    t = ceil(life_expectancy / env.params.time_period) - 1
                    if t == 0:
                        consume_fraction = min(consume_fraction, 1 / env.params.time_period) # Bound may be exceeded in continuous time case.
                    results.append(env.encode_direct_action(consume_fraction, stocks = stocks_allocation, bills = 1 - stocks_allocation))
                return results

            elif annuitize:

                results = []
                for obs in obss:
                    consume_fraction = consume_fraction_initial if env.episode_length == 0 else 1 / env.params.time_period
                    results.append(env.encode_direct_action(consume_fraction, stocks = 1, real_spias_fraction = 1))
                return results

            else:

                return None

        if search_consume_initial_around != None:

            f_cache = {}

            def f(x):

                try:

                    return f_cache[x]

                except KeyError:

                    print('    Consume: ', x)
                    for e in envs:
                        e.unwrapped.params.consume_initial = x
                    f_x, tol_x, _, _ = evaluator.evaluate(pi)
                    results = (f_x, tol_x)
                    f_cache[x] = results
                    return results

            x, f_x = gss(f, search_consume_initial_around / 2, search_consume_initial_around * 2)
            print('    Consume: ', x)
            for e in envs:
                e.unwrapped.params.consume_initial = x

        ce, ce_stderr, low, high = evaluator.evaluate(pi)

        plot(prefix, evaluator.trace, evaluator.consume_pdf)

        final_data = {
            'error': None,
            'ce': ce,
            'ce_stderr': ce_stderr,
            'ce_low': low,
            'ce_high': high,
            'consume_preretirement': envs[0].unwrapped.params.consume_preretirement_low,
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

def gss(f, a, b):
    '''Golden segment search for maximum of f on [a, b].'''

    f_a, tol_a = f(a)
    f_b, tol_b = f(b)
    tol = (tol_a + tol_b) / 2
    g = (1 + sqrt(5)) / 2
    while (b - a) > tol:
        c = b - (b - a) / g
        d = a + (b - a) / g
        f_c, tol_c = f(c)
        f_d, tol_d = f(d)
        if f_c >= f_d:
            b = d
            f_b = f_d
        else:
            a = c
            f_a = f_c
        tol = (tol_c + tol_d) / 2
    if f_a > f_b:
        found = a
        f_found = f_a
    else:
        found = b
        f_found = f_b

    return found, f_found

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
    run([environ['AIPLANNER_HOME'] + '/ai/plot'], check = True)

def main():
    parser = arg_parser()
    boolean_flag(parser, 'merton', default = False)
    boolean_flag(parser, 'samuelson', default = False)
    boolean_flag(parser, 'annuitize', default = False)
    boolean_flag(parser, 'eval-couple-net', default = True)
    parser.add_argument('--search-consume-initial-around', type = float)
        # Search for the initial consumption that maximizes the certainty equivalent using the supplied value as a hint as to where to search.
    parser.add_argument('--result-dir', default = './')
    parser.add_argument('--num-trace-episodes', type = int, default = 5)
    parser.add_argument('--num-environments', type = int, default = 10) # Number of parallel environments to use for a single model. Speeds up tensor flow.
    parser.add_argument('--pdf-buckets', type = int, default = 20) # Number of non de minus buckets to use in computing consume probability density distribution.
    training_model_params, eval_model_params, args = fin_arg_parse(parser, training = False)
    eval_model(eval_model_params, **args)

if __name__ == '__main__':
    main()
