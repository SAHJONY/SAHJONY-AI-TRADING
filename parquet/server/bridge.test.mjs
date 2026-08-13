import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { test } from 'node:test'

const snapshot=JSON.parse(execFileSync('.venv/bin/python',['parquet/bridge/snapshot.py','--desk','live','--no-log'],{encoding:'utf8'}))

test('projects all twelve transparent council personas',()=>{
  assert.equal(snapshot.schemaVersion,1)
  assert.equal(snapshot.attribution.length,12)
  assert.ok(snapshot.council.every(asset=>asset.agents.length===12))
  assert.ok(snapshot.council[0].agents[0].rationale.length>0)
})

test('Guardian blocks execution when Hermes integrity is below 80',()=>{
  if(snapshot.health.dataIntegrity<80){
    assert.equal(snapshot.health.halted,true)
    assert.match(snapshot.health.haltReason,/80% execution floor/)
  }
})

test('incubation cannot scale before 100 positive-Sharpe cycles',()=>{
  if(snapshot.incubation.positiveSharpeCycles<100)assert.equal(snapshot.incubation.scaleEligible,false)
})
