import React, { useMemo } from 'react';
import { GeoJSON, Marker, Pane, Tooltip } from 'react-leaflet';
import { divIcon, svg } from 'leaflet';
import { formatNumber } from './landingModel.js';

export const LAKE_SYMBOL = '<svg viewBox="0 0 30 24" aria-hidden="true"><path d="M7 5h16M3 12h24M7 19h16" fill="none" stroke="white" stroke-width="5" stroke-linecap="round"/><path d="M7 5h16M3 12h24M7 19h16" fill="none" stroke="#087fb7" stroke-width="2.5" stroke-linecap="round"/></svg>';
const icon=divIcon({className:'land-lake-symbol',html:LAKE_SYMBOL,iconSize:[30,24],iconAnchor:[15,12]});

export default function LakeLayer({ data, zoom, onSelect }) {
  // Separate SVG pane: no full-map canvas above the basin hit surface.
  const renderer=useMemo(()=>svg({pane:'lakePane'}),[]);
  const visible=useMemo(()=>data?{...data,features:data.features.filter(f=>Number(f.properties.area_km2)>=(zoom<7?10:zoom<9?1:0))}:null,[data,zoom]);
  if(!visible)return null;
  const symbols=visible.features.filter(f=>Number(f.properties.area_km2)>=(zoom<7?50:zoom<9?5:zoom<11?1:0));
  return <Pane name="lakePane" style={{zIndex:450}}>
    <GeoJSON key={`lakes-${zoom<7?0:zoom<9?1:2}`} data={visible} renderer={renderer}
      style={{color:'#087fb7',weight:1.2,fillColor:'#69bfdf',fillOpacity:.28}} onEachFeature={(feature,layer)=>{
        const label=document.createElement('span');label.textContent=feature.properties.display_name;
        layer.bindTooltip(label,{sticky:true});
        layer.on('click',()=>onSelect(feature.properties));
      }}/>
    {symbols.map(feature=><Marker key={feature.properties.water_body_id} icon={icon} zIndexOffset={-100}
      position={[Number(feature.properties.symbol_latitude),Number(feature.properties.symbol_longitude)]}
      title={feature.properties.display_name} eventHandlers={{click:()=>onSelect(feature.properties)}}>
      <Tooltip direction="top">{feature.properties.display_name} · {formatNumber(Number(feature.properties.area_km2))} km²</Tooltip>
    </Marker>)}
  </Pane>;
}
