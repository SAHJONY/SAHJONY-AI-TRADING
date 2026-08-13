import { useEffect, useState } from 'react'
import { CircleDot, RadioTower, SlidersHorizontal } from 'lucide-react'
import type { AgentScore, Desk, ParquetSnapshot } from './types'
import { fallbackSnapshot } from './sample'
import { AllocationPanel, AttributionPanel, BlotterPanel, BrainPanel, CouncilHeatmap, DataPanel, DriftPanel, EquityPanel, IncubationPanel, PositionsPanel, RetailSummary, RiskPanel, SourceBadge, TracePanel } from './components'

const desks:Desk[]=['live','crypto','trainer','stocks']
function useParquet(desk:Desk) {
  const [data,setData]=useState<ParquetSnapshot>(fallbackSnapshot)
  const [connected,setConnected]=useState(false)
  useEffect(()=>{
    let active=true,ws:WebSocket|undefined
    const poll=()=>fetch(`/api/snapshot?desk=${desk}`).then(r=>r.ok?r.json():Promise.reject()).then(x=>{if(active){setData(x);setConnected(true)}}).catch(()=>active&&setConnected(false))
    void poll(); const timer=window.setInterval(poll,30_000)
    if(location.hostname==='localhost'||location.hostname==='127.0.0.1'){
      ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws?desk=${desk}`)
      ws.onopen=()=>setConnected(true); ws.onclose=()=>setConnected(false)
      ws.onmessage=e=>{try{if(active)setData(JSON.parse(e.data))}catch{}}
    }
    return()=>{active=false;window.clearInterval(timer);ws?.close()}
  },[desk])
  return {data,connected}
}

export default function App(){
  const [desk,setDesk]=useState<Desk>('live'),[retail,setRetail]=useState(false),[selected,setSelected]=useState<AgentScore|null>(null)
  const {data,connected}=useParquet(desk)
  return <div className="app"><nav><div className="brand"><CircleDot/><b>PARQUET</b><span>SAHJONY CAPITAL</span></div><div className="ticker-tape">{data.council.slice(0,5).map(a=><span key={a.symbol}><b>{a.symbol.replace('/USD','')}</b> {a.price<1?a.price.toFixed(4):a.price.toLocaleString()} <i className={a.direction==='long'?'up':''}>{Math.round(a.conviction*100)}%</i></span>)}</div><div className="nav-actions"><span className={connected?'connected':''}><RadioTower/> {connected?'STREAM':'SNAPSHOT'}</span><button onClick={()=>setRetail(v=>!v)} aria-pressed={retail}><SlidersHorizontal/>{retail?'PRO TERMINAL':'RETAIL SUMMARY'}</button></div></nav><div className="deskbar"><div>{desks.map(d=><button key={d} className={desk===d?'active':''} onClick={()=>setDesk(d)}>{d}</button>)}</div><p><SourceBadge data={data}/> CYCLE {data.cycle} · {data.mode} · {data.broker} · <time>{new Date(data.ts).toLocaleTimeString()}</time></p></div>{retail?<RetailSummary data={data}/>:<main className="terminal-grid"><EquityPanel data={data}/><CouncilHeatmap data={data} onSelect={setSelected}/><BrainPanel data={data}/><AllocationPanel data={data}/><RiskPanel data={data}/><DataPanel data={data}/><BlotterPanel data={data}/><AttributionPanel data={data}/><DriftPanel data={data}/><IncubationPanel data={data}/><PositionsPanel data={data}/><TracePanel selected={selected}/></main>}<footer>PARQUET v1.1 · EVERY VALUE SOURCE-LABELED · EXECUTION AUTHORITY REMAINS IN PYTHON RISK GATES</footer></div>
}
