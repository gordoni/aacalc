# AIPlanner - Deep Learning Financial Planner
# Copyright (C) 2018 Gordon Irlam
#
# All rights reserved. This program may not be used, copied, modified,
# or redistributed without permission.
#
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.

from math import exp, log, sqrt
from random import lognormvariate, normalvariate, uniform
from statistics import mean, stdev

class Returns(object):

    def __init__(self, ret, vol, price_low, price_high, mean_reversion_rate, standard_error, time_period):

        self.ret = ret
        self.vol = vol
        self.price_low = price_low
        self.price_high = price_high
        self.mean_reversion_rate = mean_reversion_rate
        self.standard_error = standard_error
        self.time_period = time_period

        self.reset()

    def reset(self):

        m = 1 + self.ret
        self.mu = log(m / sqrt(1 + (self.vol / m) ** 2))
        self.sigma = sqrt(log(1 + (self.vol / m) ** 2))

        mu = normalvariate(self.mu, self.standard_error)

        self.period_mu = mu * self.time_period
        self.period_sigma = self.sigma * sqrt(self.time_period)
        self.above_trend = uniform(self.price_low, self.price_high)
        self.period_mean_reversion_rate = self.mean_reversion_rate * self.time_period

    def sample(self):

        sample = lognormvariate(self.period_mu, self.period_sigma) # Caution: If switch to using numpy need to get/set numpy state in fin_evaluate().

        self.above_trend *= sample / exp(self.period_mu)
        reversion = self.above_trend ** (- self.period_mean_reversion_rate)

        self.above_trend *= reversion

        return sample * reversion

    def observe(self):

        return (self.above_trend, )

def _report(name, rets):

    avg = mean(rets) - 1
    vol = stdev(rets)
    geomean = exp(mean(log(r) for r in rets)) - 1
    stderr = vol / sqrt(len(rets) - 1)

    print('    {:16s}  {:5.2%} +/- {:6.2%} (geometric {:5.2%}; stderr {:5.2%})'.format(name, avg, vol, geomean, stderr))

def yields_report(name, returns, *, duration, time_period, stepper, sample_size = 10000):

    ylds = []
    for _ in range(sample_size):
        ylds.append(exp(returns.spot(duration)))
        stepper.step()

    _report(name, ylds)

def returns_report(name, returns, *, time_period, stepper = None, sample_size = 100000, **kwargs):

    rets = []
    for _ in range(sample_size):
        rets.append(returns.sample(**kwargs) ** (1 / time_period))
        if stepper:
            stepper.step()

    _report(name, rets)
