# AACalc - Asset Allocation Calculator
# Copyright (C) 2009, 2011-2015 Gordon Irlam
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from datetime import datetime
from re import DOTALL, match

from django.http import HttpResponse
from django.test.client import RequestFactory

from aacalc.views.le import le
from aacalc.views.spia import default_spia_params, spia
from aacalc.views.utils import default_params, run_response

def healthcheck(request):

    # Life expectancy.
    request_factory = RequestFactory()
    request = request_factory.post('/calculators/le', {
        'sex': 'male',
        'age' : 65,
    })
    response = le(request)
    page = response.content
    cohort, cohort95 = match('^.*<table id="ssa_cohort".*?<td class="right">(.*?)</td>.*?<span.*?>(.*?)</span>.*$', page, DOTALL).groups()
    assert(17 < float(cohort) < 20)
    assert(31 < float(cohort95) < 35)
    cohort_healthy, cohort_healthy95 = match('^.*<table id="iam".*?<td class="right">(.*?)</td>.*?<span.*?>(.*?)</span>.*$', page, DOTALL).groups()
    assert(22 < float(cohort_healthy) < 25)
    assert(34 < float(cohort_healthy95) < 40)
    period, = match('^.*<table id="ssa_period".*?<td class="right">.*?<span.*?>(.*?)</span>.*$', page, DOTALL).groups()
    assert(17 < float(period) < 20)

    # SPIA.
    today = datetime.utcnow().date()
    request_factory = RequestFactory()
    params = default_spia_params()

    params['payout'] = 1000
    request = request_factory.post('/calculators/spia', params)
    response = spia(request)
    page = response.content
    premium1, premium2, yield_curve_date = match('^.*Actuarially fair premium:.*?(\d+),(\d+).*?Yield curve date: (\d\d\d\d-\d\d-\d\d).*$', page, DOTALL).groups()
    assert(150000 < int(premium1 + premium2) < 300000)
    quote = datetime.strptime(yield_curve_date, '%Y-%m-%d').date()
    assert(0 <= (today - quote).days <= 8)

    params['real'] = False
    request = request_factory.post('/calculators/spia', params)
    response = spia(request)
    page = response.content
    premium1, premium2, yield_curve_date = match('^.*Actuarially fair premium:.*?(\d+),(\d+).*?Yield curve date: (\d\d\d\d-\d\d).*$', page, DOTALL).groups()
    assert(100000 < int(premium1 + premium2) < 200000)
    quote = datetime.strptime(yield_curve_date, '%Y-%m').date()
    assert(0 <= (today - quote).days <= 80)

    # Asset allocation.
    scenario_dict = dict(default_params)
    scenario_dict['sex'] = 'male'
    scenario_dict['dob'] = 90
    scenario_dict['p'] = 100000
    scenario_dict['retirement_year'] = 2000
    request = request_factory.post('/calculators/aa', scenario_dict)
    response = run_response(request, scenario_dict, True)
    page = response.content
    consume, = match('^.*Suggested initial annual consumption amount: (\d+).*$', page, DOTALL).groups()
    assert(30000 < int(consume) < 50000)
    stocks, = match('^.*Suggested initial asset allocation stocks/bonds: (\d+)/\d+.*$', page, DOTALL).groups()
    assert(80 <= int(stocks) <= 100)
    return HttpResponse('OK', content_type = 'text/plain')
