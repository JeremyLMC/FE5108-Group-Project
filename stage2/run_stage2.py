"""Reproduce Track A Stage 2 from the frozen, cleaned Stage 1 inputs."""
from pathlib import Path
import json
import hashlib
import platform
import importlib.metadata
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

BASE = Path(__file__).resolve().parent

def main():
    for name in ('results', 'figures', 'validation'):
        (BASE / name).mkdir(exist_ok=True)
    returns = pd.read_csv(BASE/'data/returns_us_monthly.csv', index_col='Month', float_precision='round_trip')
    factors = pd.read_csv(BASE/'data/ff3_monthly.csv', index_col='Month', float_precision='round_trip')
    expected = pd.period_range('2015-11', '2026-08', freq='M').astype(str).tolist()
    assert returns.index.is_unique and factors.index.is_unique
    assert returns.index.tolist() == factors.index.tolist() == expected
    assert returns.shape == (130, 29)
    assert np.isfinite(returns.values).all() and np.isfinite(factors.values).all()
    excess = returns.sub(factors.RF, axis=0)
    market = factors['Mkt-RF']  # Already excess return and already decimal.
    X = sm.add_constant(market)
    rows = []
    for ticker in returns:
        m = sm.OLS(excess[ticker], X).fit()
        rows.append(dict(Ticker=ticker, Alpha_monthly=m.params['const'], Beta=m.params['Mkt-RF'],
                         t_Alpha=m.tvalues['const'], p_Alpha=m.pvalues['const'], R_squared=m.rsquared, N=int(m.nobs)))
        assert abs(excess[ticker].mean() - m.params['const'] - m.params['Mkt-RF']*market.mean()) < 1e-12
    capm = pd.DataFrame(rows)
    capm.to_csv(BASE/'results/capm_results.csv', index=False)
    points = capm[['Ticker', 'Beta']].copy()
    points['Mean_excess_return'] = points.Ticker.map(excess.mean())
    cross = sm.OLS(points.Mean_excess_return, sm.add_constant(points.Beta)).fit()
    a, b, premium = cross.params['const'], cross.params['Beta'], market.mean()
    points.to_csv(BASE/'results/sml_points.csv', index=False)
    pd.DataFrame([['Empirical fitted SML',a,b],['Theoretical CAPM SML',0,premium]],
                 columns=['Line','Intercept','Slope']).to_csv(BASE/'results/sml_summary.csv',index=False)
    tests = capm.copy()
    tests['Abs_t_Alpha'] = tests.t_Alpha.abs()
    tests['Abs_t_gt_2'] = tests.Abs_t_Alpha > 2
    tests['p_lt_0_05'] = tests.p_Alpha < .05
    tests.to_csv(BASE/'results/alpha_tests.csv', index=False)
    sig = tests.loc[tests.Abs_t_gt_2]
    pd.DataFrame([dict(Number_of_assets=29, Criterion='|t(Alpha)| > 2',
        Observed_significant_count=len(sig), Approx_expected_count_under_H0=29*.05,
        Significant_tickers=', '.join(sig.Ticker))]).to_csv(BASE/'results/alpha_assessment.csv',index=False)
    comparison = pd.DataFrame([
        ['Intercept',a,0,a], ['Slope',b,premium,b-premium]],
        columns=['Parameter','Empirical_monthly','Theory_monthly','Difference_monthly'])
    comparison.to_csv(BASE/'results/sml_comparison.csv',index=False)
    points['CAPM_predicted_excess_return'] = points.Beta*premium
    points['Deviation_from_CAPM'] = points.Mean_excess_return-points.CAPM_predicted_excess_return
    assert np.allclose(points.Deviation_from_CAPM, capm.Alpha_monthly)
    points.to_csv(BASE/'results/pricing_deviations.csv',index=False)
    grid = np.linspace(0,1.55,300)
    fig,ax = plt.subplots(figsize=(9,5.1))
    ax.scatter(points.Beta,points.Mean_excess_return,s=30,color='#245A81',label='29 stocks',zorder=3)
    ax.plot(grid,a+b*grid,color='#D17A22',lw=2,label='Empirical fitted SML')
    ax.plot(grid,premium*grid,color='#36845B',lw=2,ls='--',label='Theoretical CAPM SML')
    offsets={'KO':(-14,-12),'JNJ':(-8,8),'MCD':(7,-12),'WMT':(-9,8),'PG':(-10,-12),
             'VZ':(-16,-12),'CVX':(-18,-12),'AXP':(5,-12),'GE':(-7,-12),
             'CSCO':(5,8),'IBM':(-14,-12),'HD':(5,-12),'GS':(5,5),'INTC':(-13,9)}
    for r in points.itertuples():
        ax.annotate(r.Ticker,(r.Beta,r.Mean_excess_return),xytext=offsets.get(r.Ticker,(4,4)),textcoords='offset points',fontsize=7)
    ax.axhline(0,color='gray',lw=.6)
    ax.set(xlabel='Estimated CAPM beta',ylabel='Mean monthly excess return',xlim=(0,1.55))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.grid(alpha=.15);ax.legend(fontsize=8,loc='upper left');fig.tight_layout()
    fig.savefig(BASE/'figures/empirical_sml.png',dpi=300);plt.close(fig)
    summary = dict(sample_start=expected[0],sample_end=expected[-1],T=130,N=29,
        empirical_intercept=a,empirical_slope=b,theoretical_slope=premium,
        slope_ratio=b/premium,slope_shortfall_fraction=1-b/premium,
        crossing_beta=a/(premium-b),cross_section_R_squared=cross.rsquared,
        observed_significant_alphas=len(sig),approx_expected_false_positives=1.45,
        significant_tickers=sig.Ticker.tolist(),inference='Conventional OLS; no Holm correction or GRS test')
    (BASE/'results/stage2_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    validation=dict(status='passed',checks=['130 contiguous common months; 29 assets; finite inputs',
        'OLS mean identity holds for every stock', 'SML pricing deviations equal time-series alphas'],
        inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'data').glob('*.csv')},
        python=platform.python_version(),packages={p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','statsmodels','matplotlib']})
    (BASE/'validation/reproduction.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(capm.to_string(index=False));print('\nExhibit 2d\n'+comparison.to_string(index=False));print(json.dumps(summary,indent=2))
    return summary

if __name__ == '__main__':
    main()
