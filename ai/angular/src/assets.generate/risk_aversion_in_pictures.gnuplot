#!/usr/bin/gnuplot

set datafile separator ','
set terminal svg dynamic size 800,400

set xlabel "consumption"
set xrange [0:*]
set xtics 0, 100, 1

set ylabel "probability"
set yrange [0:*]
unset ytics

set output 'risk_aversion_pdf.svg'
plot 'risk_aversion_1_pdf.csv' using 1:2 with lines title 'RRA = 1', \
    'risk_aversion_3_pdf.csv' using 1:2 with lines title 'RRA = 3', \
    'risk_aversion_6_pdf.csv' using 1:2 with lines title 'RRA = 6'