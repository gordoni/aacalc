# AIPlanner - Deep Learning Financial Planner
# Copyright (C) 2018-2019 Gordon Irlam
#
# All rights reserved. This program may not be used, copied, modified,
# or redistributed without permission.
#
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.

from math import exp, log

class Utility(object):

    def __init__(self, gamma, floor):

        self.gamma = gamma

        self.utility_scale = 1 # Temporary scale for _inverse_utility().
        self.utility_scale = floor / self.inverse(-1) # Make utility(consume_floor) = -1.

    def utility(self, c):

        if c == 0 and self.gamma >= 1:
            return float('-inf')

        if self.gamma == 1:
            return log(c / self.utility_scale)
        else:
            return (c / self.utility_scale) ** (1 - self.gamma) / (1 - self.gamma)
                # Incompatible with gamma=1, because not shifted so that utility(utility_scale) = 0.
                # We do not shift to avoid losing any possible floating point precision.

    def inverse(self, u):

        if u == float('-inf') and self.gamma >= 1:
            return 0

        if self.gamma == 1:
            return exp(u) * self.utility_scale
        else:
            return (u * (1 - self.gamma)) ** (1 / (1 - self.gamma)) * self.utility_scale