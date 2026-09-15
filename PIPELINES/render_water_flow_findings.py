"""Render model comparisons and explicitly hypothetical recoverability arithmetic."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIPELINES.render_water_flow_diagram import plt,save,FLOW


def render():
    data=json.loads((FLOW/'regional-water-flow-sensitivity.json').read_text())
    fig,axes=plt.subplots(2,1,figsize=(12.5,8),sharex=True)
    years=[r['year'] for r in data['annual']]
    for v,c in [('pre_mm_s','#2469a0'),('aet_mm_s','#bc732e')]:
        axes[0].plot(years,[r.get(v) for r in data['annual']],label=data['variables'][v]['label'],color=c,lw=2)
    for v,c,label in [('p_minus_aet_km3','#278367','TerraClimate P − AET'),('run_mm_s','#8f589c','ERA5-Land runoff'),('rtc_mm_s','#2469a0','TerraClimate runoff')]:
        if v=='rtc_mm_s' and data['variables'][v]['status']!='available':continue
        axes[1].plot(years,[r.get(v) for r in data['annual']],label=label,color=c,lw=2)
    for ax in axes:
        ax.set(ylabel='Modelled volume (km³/year)',ylim=(0,None))
        ax.grid(alpha=.15);ax.legend(loc='upper right',fontsize=10,frameon=False,ncol=2)
    axes[1].set_xlabel('Calendar year'); axes[1].set_xticks(years[::2])
    fig.suptitle('Land-water estimates on the same domain and years',fontsize=17,x=.07,ha='left')
    fig.text(.07,.925,f"{data['domain']['basins']:,} basins • {data['domain']['area_km2']:,.1f} km² • annual totals require all 12 months in every basin",fontsize=10)
    fig.text(.07,.025,'No withdrawal threshold is drawn: these estimates are neither gauged discharge nor a complete managed-river water balance.',fontsize=10)
    fig.subplots_adjust(left=.085,right=.97,top=.87,bottom=.11,hspace=.23)
    save(fig,'regional-water-flow-sensitivity.svg')
    cases=data['efficiency_example']['cases']
    fig,ax=plt.subplots(figsize=(11,4.8))
    x=range(len(cases));w=.32
    ax.bar([i-w/2 for i in x],[r['gross_withdrawal_reduction_units'] for r in cases],w,label='Gross withdrawal reduction',color='#788fa2')
    ax.bar([i+w/2 for i in x],[r['net_downstream_gain_units'] for r in cases],w,label='Net gain under stated assumptions',color='#24816b')
    ax.set(xticks=list(x),xticklabels=['0% recoverable','50% recoverable','100% recoverable'],ylim=(0,18),ylabel='Units per 100 initially withdrawn')
    ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True);ax.legend(frameon=False,fontsize=10)
    fig.suptitle('Reduced withdrawal does not equal basin water saved',x=.08,ha='left',fontsize=16)
    fig.text(.08,.89,'Illustration only: delivery efficiency 0.63 → 0.73, fixed delivered demand, no rebound.',fontsize=10)
    fig.text(.08,.035,'Recoverability is hypothetical. These are not country targets, confidence intervals or km³/year forecasts. Accounting principle: FAO.',fontsize=9)
    fig.subplots_adjust(left=.08,right=.97,top=.79,bottom=.17)
    save(fig,'regional-water-flow-pathway.svg')


if __name__=='__main__':render()
