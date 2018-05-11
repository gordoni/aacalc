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
from random import lognormvariate, normalvariate

class Returns(object):

    def __init__(self, ret, vol, standard_error, time_period):

        self.ret = normalvariate(ret, standard_error)
        self.vol = vol
        self.time_period = time_period

        m = 1 + self.ret
        self.mu = log(m / sqrt(1 + (self.vol / m) ** 2))
        self.sigma = sqrt(log(1 + (self.vol / m) ** 2))

        self.period_mu = self.mu * time_period
        self.period_sigma = self.sigma * sqrt(time_period)

    def sample(self):

        return lognormvariate(self.period_mu, self.period_sigma) # Caution: If switch to using numpy need to get/set numpy state in fin_evaluate().
