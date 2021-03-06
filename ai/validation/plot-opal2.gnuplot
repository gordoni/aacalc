#!/usr/bin/gnuplot

# AIPlanner - Deep Learning Financial Planner
# Copyright (C) 2018 Gordon Irlam
#
# All rights reserved. This program may not be used, copied, modified,
# or redistributed without permission.
#
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.

set datafile separator ","
set terminal svg dynamic size 800,600

set xlabel "age"
set ylabel "investments"
set yrange [0:1000000]
set format y "%.1s%c"

set xrange [65.999:100.001]
set zlabel "consumption"
set zrange [0:200000]
set format z "%.0s%c"
set output "run.opal.ssa_40_plus_3_female-iid_bonds/opal-consume.svg"
splot "run.opal.ssa_40_plus_3_female-iid_bonds/opal-linear.csv" using 1:2:7 every :2 with lines title "Stochastic dynamic programming"
set output "run.opal.ssa_40_plus_3_female-iid_bonds-gamma6/opal-consume.svg"
splot "run.opal.ssa_40_plus_3_female-iid_bonds-gamma6/opal-linear.csv" using 1:2:7 every :2 with lines title "Stochastic dynamic programming"
set output "run.opal.ssa_40_plus_3_female-iid_bonds-stocks_return0.05/opal-consume.svg"
splot "run.opal.ssa_40_plus_3_female-iid_bonds-stocks_return0.05/opal-linear.csv" using 1:2:7 every :2 with lines title "Stochastic dynamic programming"

set xrange [40:100.001]
set yrange [33333:1000000] # Opal aa varies randomly at zero.
set ytics 200000
set zlabel "stocks"
set zrange [0:100]
set format z "%g%%"
set output "run.opal.ssa_40_plus_3_female-iid_bonds/opal-stocks.svg"
splot "run.opal.ssa_40_plus_3_female-iid_bonds/opal-linear.csv" using 1:2:($9 * 100) every :2 with lines title "Stochastic dynamic programming"
set output "run.opal.ssa_40_plus_3_female-iid_bonds-gamma6/opal-stocks.svg"
splot "run.opal.ssa_40_plus_3_female-iid_bonds-gamma6/opal-linear.csv" using 1:2:($9 * 100) every :2 with lines title "Stochastic dynamic programming"
set output "run.opal.ssa_40_plus_3_female-iid_bonds-stocks_return0.05/opal-stocks.svg"
splot "run.opal.ssa_40_plus_3_female-iid_bonds-stocks_return0.05/opal-linear.csv" using 1:2:($9 * 100) every :2 with lines title "Stochastic dynamic programming"
