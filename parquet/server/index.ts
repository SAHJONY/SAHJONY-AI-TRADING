import cors from 'cors'
import express from 'express'
import { createServer } from 'node:http'
import { spawn } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { WebSocketServer } from 'ws'
import type { Desk, ParquetSnapshot } from '../ui/src/types.js'

const here=dirname(fileURLToPath(import.meta.url)), root=resolve(here,'../..')
const allowed=new Set<Desk>(['live','crypto','trainer','stocks'])
const cache=new Map<Desk,ParquetSnapshot>()
const clientDesks=new WeakMap<object,Desk>()

function bridge(desk:Desk):Promise<ParquetSnapshot>{
  return new Promise((ok,fail)=>{
    const python=process.env.PYTHON_BIN || resolve(root,'.venv/bin/python')
    const child=spawn(python,[resolve(root,'parquet/bridge/snapshot.py'),'--desk',desk],{cwd:root})
    let out='',err=''; child.stdout.on('data',b=>out+=b); child.stderr.on('data',b=>err+=b)
    child.on('error',fail); child.on('close',code=>code===0?ok(JSON.parse(out)):fail(new Error(err||`bridge exited ${code}`)))
  })
}
function deskOf(value:unknown):Desk{return allowed.has(value as Desk)?value as Desk:'live'}
async function refresh(desk:Desk){const snapshot=await bridge(desk);cache.set(desk,snapshot);return snapshot}

const app=express(); app.use(cors()); app.use(express.json())
app.get('/api/health',(_req,res)=>res.json({ok:true,service:'parquet',executionAuthority:false}))
app.get('/api/snapshot',async(req,res)=>{try{res.json(await refresh(deskOf(req.query.desk)))}catch(error){res.status(503).json({error:error instanceof Error?error.message:'bridge unavailable'})}})
const server=createServer(app),wss=new WebSocketServer({server,path:'/ws'})
wss.on('connection',async(socket,request)=>{const url=new URL(request.url||'/ws','http://localhost'),desk=deskOf(url.searchParams.get('desk'));clientDesks.set(socket,desk);try{socket.send(JSON.stringify(cache.get(desk)||await refresh(desk)))}catch{socket.close(1011,'snapshot unavailable')}})
setInterval(async()=>{for(const desk of new Set([...wss.clients].filter(c=>c.readyState===1).map(c=>clientDesks.get(c)??'live'))){try{const data=await refresh(desk);for(const client of wss.clients)if(client.readyState===1&&clientDesks.get(client)===desk)client.send(JSON.stringify(data))}catch(error){console.error(error)} }},30_000).unref()
const port=Number(process.env.PARQUET_PORT||8788);server.listen(port,'127.0.0.1',()=>console.log(`Parquet bridge listening on http://127.0.0.1:${port}`))
