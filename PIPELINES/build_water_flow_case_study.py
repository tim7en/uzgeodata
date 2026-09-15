"""Rebuild the bounded water-flow study and its directory card, without acquisition."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ATLAS_MODULES.core.runtime import write_json
from PIPELINES import build_water_flow_diagram as accounts
from PIPELINES import build_water_flow_sensitivity as diagnostics
from PIPELINES import render_water_flow_diagram as figures
from PIPELINES import render_water_flow_findings as findings
from PIPELINES import build_water_flow_page as page


def main():
    accounts.build();diagnostics.build();figures.render();figures.overview();findings.render();page.build()
    path=ROOT/'PUBLISHED/data/case-studies/study-directory.json'
    if path.exists():
        directory=json.loads(path.read_text())
        card=accounts.study_card()
        matches=[i for i,s in enumerate(directory['studies']) if s['id']=='water-flow']
        if len(matches)!=1:raise ValueError('Expected one water-flow directory entry')
        directory['studies'][matches[0]]=card
        # Other studies keep their own build/evidence dates.
        directory['water_flow_updated_at']=card['evidence_date']
        write_json(path,directory)
    print('Built source-audited water-flow case study, maps and directory card.')


if __name__=='__main__':main()
