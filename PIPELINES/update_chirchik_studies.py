"""Refresh case-study inputs and rebuild the reviewable scientific products.

Run --offline to reproduce analyses from downloaded tables. This refresh does
not change observed records or remove scientific readiness gates.
"""
import argparse
import subprocess
import sys
from datetime import datetime,timezone
from build_chirchik_case_studies import ROOT,OUT,write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--offline',action='store_true');args=parser.parse_args()
    year=datetime.now(timezone.utc).year
    tasks=[('Observation audit',['build_chirchik_case_studies.py'])]
    if not args.offline:
        tasks += [('Station products',['extract_case_study_forcing.py']),
            ('Historical basin climate',['extract_chirchik_remote.py','--task','climate']),
            ('Terra and Aqua snow',['extract_chirchik_remote.py','--task','snow','--sensors','terra','aqua']),
            ('Latest combined snow',['extract_chirchik_remote.py','--task','snow','--sensors','combined','--end',str(year)]),
            ('Charvak water extent',['extract_chirchik_remote.py','--task','reservoir']),
            ('Charvak sensor check',['extract_chirchik_remote.py','--task','reservoir-check']),
            ('Terrain and land cover',['extract_chirchik_environment.py','--task','profiles']),
            ('Latest energy inputs',['extract_chirchik_environment.py','--task','energy','--end',str(year)])]
    tasks += [('Historical verification',['analyse_chirchik_validation.py']),('Observation page',['build_chirchik_case_studies.py']),
        ('Physical, forest and Bayesian models',['model_chirchik_water.py']),('Observation figure',['plot_chirchik_case_studies.py']),
        ('Reports, figure atlas and workbook',['report_chirchik_environment.py'])]
    status={'started_at':datetime.now(timezone.utc).isoformat(),'mode':'offline' if args.offline else 'refresh','status':'running','completed':0,'total':len(tasks),'steps':[]}
    try:
        for label,command in tasks:
            status['current_step']=label;write_json(OUT/'pipeline-status.json',status)
            print(f"[{status['completed']+1}/{len(tasks)}] {label}",flush=True)
            subprocess.run([sys.executable,str(ROOT/'PIPELINES'/command[0]),*command[1:]],cwd=ROOT,check=True)
            status['completed']+=1;status['steps'].append(label)
        status.update(status='complete',finished_at=datetime.now(timezone.utc).isoformat(),current_step=None)
    except Exception as error:
        status.update(status='failed',error=str(error),finished_at=datetime.now(timezone.utc).isoformat())
        raise
    finally:write_json(OUT/'pipeline-status.json',status)


if __name__=='__main__':main()
