"""Render zero-based comparisons and an actual geographic overview from audited inputs."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.patches import Polygon, Patch
from shapely.geometry import shape

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIPELINES.build_water_flow_diagram import digest
FLOW=ROOT/'PUBLISHED/data/water-flow'
COLOURS={'tajikistan':'#087f8c','turkmenistan':'#bd591c','uzbekistan':'#247645'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,
 'axes.spines.right':False,'svg.fonttype':'none','svg.hashsalt':'water-flow-audit-v2','axes.titleweight':'bold'})


def save(fig,name):
    fig.savefig(FLOW/name,format='svg',metadata={'Date':None},facecolor='#fcfcfa')
    preview=ROOT/'WORKSPACE/water-flow-review';preview.mkdir(parents=True,exist_ok=True)
    fig.savefig(preview/Path(name).with_suffix('.png').name,dpi=130,facecolor='#fcfcfa')
    plt.close(fig)


def render():
    data=json.loads((FLOW/'regional-water-flow.json').read_text())
    fig,axes=plt.subplots(1,3,figsize=(13,5.4),sharex=True,sharey=True)
    for ax,year in zip(axes,data['years']):
        rows=[r for r in data['country_withdrawals'] if r['year']==year]
        for i,r in enumerate(rows):
            ax.barh(i,r['withdrawal_km3'],height=.46,color=COLOURS[r['country']])
            ax.plot(r['limit_km3'],i,'|',markersize=22,markeredgewidth=2.2,color='#253743')
            ax.text(r['withdrawal_km3']+.3,i+.03,f"{r['withdrawal_km3']:.2f}",fontsize=10,va='center')
        ax.set(yticks=range(3),yticklabels=[r['country'].title() for r in rows],xlim=(0,27),xlabel='Withdrawal (km³/year)',title=str(year))
        ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    axes[0].invert_yaxis()
    fig.suptitle('Amu Darya: country withdrawals and allocation limits',fontsize=17,x=.04,ha='left')
    fig.text(.04,.88,'Bars = reported actual withdrawals. Vertical ticks = limits. January–December; identical axes.',fontsize=11)
    fig.text(.04,.04,'SIC ICWC yearbooks 2022–2024, §2.1. These are withdrawal accounts, not country river inflows/outflows.',fontsize=10)
    fig.subplots_adjust(left=.12,right=.97,top=.78,bottom=.2,wspace=.18)
    save(fig,'regional-water-flow.svg')

    fig,ax=plt.subplots(figsize=(12.5,4.6))
    labels={'northern_aral':'Northern Aral • Syr Darya','amu_delta':'Amu delta • river + canals + drains','large_aral':'Large Aral • South Karakalpak drain'}
    colours=['#245ba4','#10836f','#8d609a']
    for i,(scope,label) in enumerate(labels.items()):
        rows=[r for r in data['environmental_deliveries'] if r['scope']==scope]
        ax.bar([r['year']+(i-1)*.23 for r in rows],[r['volume_km3'] for r in rows],width=.21,color=colours[i],label=label)
    ax.set(xticks=data['years'],ylim=(0,3.2),ylabel='Reported delivery (km³/year)')
    ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Downstream deliveries are separate reporting points',x=.07,ha='left',fontsize=16)
    ax.legend(loc='upper left',fontsize=10,frameon=False,ncol=1)
    fig.text(.07,.035,'The South Karakalpak drain bypasses the delta. These columns are not a connected flow partition. Source: SIC ICWC §2.1–2.2.1.',fontsize=9)
    fig.subplots_adjust(top=.83,bottom=.2,left=.07,right=.98)
    save(fig,'regional-water-flow-deliveries.svg')
    return data


def overview():
    from ATLAS_MODULES.core.runtime import write_json
    base=ROOT/'PUBLISHED/data/hydroclimate'
    files=['basins-level07.geojson','reference-rivers-main.geojson','dams-transboundary.geojson']
    datasets=[json.loads((base/f).read_text()) for f in files]
    colours={'amu_darya':'#d5e9dc','syr_darya':'#d4e5f4'}
    fig,ax=plt.subplots(figsize=(12,6.4))
    for feature in datasets[0]['features']:
        geom=shape(feature['geometry']).simplify(.018,preserve_topology=True)
        parts=[geom] if geom.geom_type=='Polygon' else geom.geoms
        for poly in parts:
            ax.add_patch(Polygon(list(poly.exterior.coords),facecolor=colours.get(feature['properties'].get('system_id'),'#e5e5e0'),edgecolor='#97ada7',linewidth=.18))
    lines=[]
    for feature in datasets[1]['features']:
        g=shape(feature['geometry']).simplify(.012)
        parts=[g] if g.geom_type=='LineString' else g.geoms
        lines.extend(list(line.coords) for line in parts)
    ax.add_collection(LineCollection(lines,colors='#367caa',linewidths=.45,alpha=.7))
    sites=[]
    for f in datasets[2]['features']:
        name=f['properties'].get('dam_name','')
        if any(s in name.lower() for s in ['toktogul','nurek','tuyam','chardara','shardara']):
            x,y=f['geometry']['coordinates'][:2]
            ax.scatter(x,y,s=30,c='#223a4a',marker='s',zorder=5)
            ax.annotate(name,(x,y),xytext=(5,5),textcoords='offset points',fontsize=9,
                        bbox=dict(facecolor='white',alpha=.85,edgecolor='none',pad=1),zorder=6)
            sites.append(dict(name=name,longitude=x,latitude=y,source='dams-transboundary.geojson',position_source=f['properties'].get('position_source')))
    ax.autoscale();ax.set_aspect(1/math.cos(math.radians(40)))
    ax.set(xlabel='Longitude (°E)',ylabel='Latitude (°N)')
    ax.grid(alpha=.18)
    ax.legend(handles=[Patch(facecolor=c,label=k.replace('_',' ').title()) for k,c in colours.items()],loc='lower left',framealpha=.95)
    fig.suptitle('Study geography • Amu Darya and Syr Darya systems',x=.07,ha='left',fontsize=16)
    fig.text(.07,.925,'Published basin outlines and river network; squares identify mapped dams and reporting landmarks.',fontsize=10)
    fig.text(.07,.025,'HydroBASINS/HydroRIVERS and the project dam inventory. Display geometry simplified; colours show basin systems, not countries.',fontsize=9)
    fig.subplots_adjust(left=.07,right=.98,bottom=.12,top=.88)
    save(fig,'regional-water-flow-map.svg')
    write_json(FLOW/'regional-water-flow-map.json',dict(type='geographic_overview',crs='EPSG:4326',
      display_simplification_degrees=.018,not_for_area_calculation=True,sites=sites,
      source_files={str((base/f).relative_to(ROOT)):digest(base/f) for f in files}))


if __name__=='__main__':
    render();overview();print('Rendered withdrawal, delivery and geographic figures')
