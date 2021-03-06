/*
 * AACalc - Asset Allocation Calculator
 * Copyright (C) 2009, 2011-2015 Gordon Irlam
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

package com.gordoni.opal;

abstract class Utility
{
        public double u_0 = Double.NaN;
        public double u_inf = Double.NaN;

        public abstract double utility(double c);

        public abstract double inverse_utility(double u);

        public abstract double slope(double c);

        public abstract double inverse_slope(double s);

        public abstract double slope2(double c);

        protected void set_constants()
        {
                u_0 = utility(0);
                u_inf = utility(Double.POSITIVE_INFINITY);
        }

        public static Utility utilityFactory(Config config, String utility_function, Double eta, double beta, Double alpha, double c_shift, double c_zero, Double ce, double ce_ratio, double c1, double s1, double c2, double s2, double public_assistance, double public_assistance_phaseout_rate)
        {
                boolean linear = utility_function.equals("linear");
                if (utility_function.equals("power") && ((eta == null && s1 == s2) || (eta != null && eta == 0)) && public_assistance == 0)
                        linear = true;
                else if (utility_function.equals("exponential") && ((alpha == null && s1 == 0) || (alpha != null && alpha == 0)) && public_assistance == 0)
                {
                        assert(s2 == 0); // public_assistance must be positive if utility_consume_fn="power" and utility_inherit_fn="exponential" unless force_alpha.
                        linear = true;
                }
                if (linear)
                {
                        assert(public_assistance == 0);
                        return new UtilityLinear(c_zero, s2);
                }
                else if (utility_function.equals("power"))
                        return new UtilityPower(config, eta, c_shift, c_zero, 0, ce, ce_ratio, c1, s1, c2, s2, public_assistance, public_assistance_phaseout_rate, null);
                else if (utility_function.equals("exponential"))
                        return new UtilityExponential(config, alpha, c_shift, c_zero, c1, s1, c2, s2, public_assistance, public_assistance_phaseout_rate);
                else if (utility_function.equals("hara"))
                        return new UtilityHara(config, eta, beta, c_shift, c_zero, c2, s2, public_assistance, public_assistance_phaseout_rate, null);
                else
                        assert(false);
                return null;
        }

        public static Utility joinFactory(Config config, String join_function, Utility utility1, Utility utility2, double c1, double c2)
        {
                if (join_function.equals("ara"))
                        return new UtilityJoinAra(config, utility1, utility2, c1, c2);
                else if (join_function.startsWith("slope-"))
                        return new UtilityJoinSlope(config, join_function, utility1, utility2, c1, c2);
                else
                        assert(false);
                return null;
        }
}
