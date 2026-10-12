// Deterministic demonstration rules. All extracted facts retain original excerpts.
export const STATUS = ['Confirmed shortfall','Potential risk','Unknown','On track','Resolved'];
export const CAUSES = ['Capacity shortage','Material shortage','Quality issue','Machine failure','Workforce constraint','Logistics issue','Customs issue','Sub-supplier issue','Order misunderstanding','Commercial hold','Force majeure','Cause not provided','Other'];
export const DAY = 86400000;
export const dateMs = value => Date.parse(String(value).slice(0,10)+'T00:00:00Z');
export const days = (a,b) => Math.round((dateMs(a)-dateMs(b))/DAY);
export function addDays(value,n){return new Date(dateMs(value)+n*DAY).toISOString().slice(0,10);}
export function validDate(value){if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return false;const d=new Date(dateMs(value));return !isNaN(d)&&d.toISOString().slice(0,10)===value;}
export function businessAge(asOf,received){let count=0;for(let d=dateMs(received)+DAY;d<=dateMs(asOf);d+=DAY){const w=new Date(d).getUTCDay();if(w!==0&&w!==6)count++;}return count;}
export function inScope(line,state){const d=days(line.required_date,state.as_of);return d>=0&&d<state.settings.horizon&&line.open_qty>0&&!line.deleted&&!line.finally_delivered;}
export function current(line){return [...line.commitments].sort((a,b)=>b.received.localeCompare(a.received)||b.id.localeCompare(a.id))[0]||null;}
export function evidenceFresh(line,commitment,state){if(!commitment)return false;const horizon=days(line.required_date,state.as_of);if(days(state.as_of,commitment.received)<0)return false;return horizon<28?businessAge(state.as_of,commitment.received)<=state.settings.near_business_days:days(state.as_of,commitment.received)<=(horizon<56?state.settings.mid_calendar_days:state.settings.far_calendar_days);}
export function assess(line,state){
  const c=current(line),k=state.cases.find(x=>x.id===line.case_id),reasons=[],missing=[];
  const legs=c?.legs||[],total=legs.reduce((a,b)=>a+b.qty,0),onTime=legs.filter(x=>x.date<=line.required_date).reduce((a,b)=>a+b.qty,0);
  const fresh=evidenceFresh(line,c,state),age=c?days(state.as_of,c.received):null;
  const sapConflict=!!c&&legs.length>0&&line.sap_qty!==null&&(total!==line.sap_qty||legs.some(x=>x.date!==line.sap_date));
  const conflict=!!c&&(c.conflict||(sapConflict&&!c.reviewed));
  if(!c){missing.push('A current supplier commitment');reasons.push('No supplier evidence is available.');}
  if(c&&!legs.length){missing.push('A firm delivery date and quantity');reasons.push('The supplier has not made a complete commitment.');}
  if(c&&legs.length&&onTime<line.open_qty){reasons.push(`${line.open_qty-onTime} ${line.uom} are not covered by the required date.`);if(total<line.open_qty)missing.push('Quantity and delivery date for the remaining balance');}
  if(c&&legs.length&&onTime<line.open_qty&&!c.cause)missing.push('Cause of the deviation');
  if(c&&legs.length&&onTime<line.open_qty&&!c.recovery)missing.push('A recovery action');
  if(c&&!c.dispatch)missing.push('Expected dispatch date');
  if(c&&!c.next_update)missing.push('The next reliable update date');
  if(c&&!fresh)reasons.push('Supplier evidence is outside the freshness threshold.');
  if(conflict)reasons.push(c.conflict?'Supplier statements contain an unresolved conflict.':'The supplier statement differs from the SAP confirmation.');
  if(c?.uncertain)reasons.push('The supplier explicitly describes uncertainty.');
  const overdue=state.requests.some(r=>r.status==='Awaiting supplier'&&r.deadline<state.as_of&&r.lines.includes(line.id)&&!(r.answered_lines||[]).includes(line.id));
  if(overdue)reasons.push('The clarification response is overdue.');
  if(line.manual_flag)reasons.push('The buyer flagged this schedule line for attention.');
  const missedDispatch=!!(c?.dispatch&&c.dispatch<state.as_of&&!c.dispatched);
  if(missedDispatch)reasons.push('The stated dispatch date has passed; shipment is unverified.');
  let status=!c?'Unknown':legs.length&&onTime<line.open_qty?'Confirmed shortfall':(!legs.length||!fresh||conflict||c.uncertain||overdue||line.manual_flag||missedDispatch)?'Potential risk':'On track';
  if(k?.closed)status='Resolved';
  let information=conflict?'Conflicting information':c&&!fresh?'Outdated information':missing.length?'Missing critical information':'Complete';
  return {status,information,reasons,missing,total,onTime,shortfall:c&&legs.length?Math.max(0,line.open_qty-onTime):null,fresh,age,conflict,sapConflict,commitment:c,reviewed:!!c?.reviewed,overdue};
}
export function supplierSummary(supplier,state){
  const lines=state.lines.filter(x=>x.supplier_id===supplier.id&&inScope(x,state)),assessments=lines.map(x=>assess(x,state));
  const status=STATUS.find(s=>assessments.some(a=>a.status===s))||'Unknown';
  return {supplier,lines,assessments,status,attention:assessments.filter(a=>!['On track','Resolved'].includes(a.status)).length,shortfall:assessments.reduce((sum,a)=>sum+(a.shortfall||0),0),next:lines.map(x=>x.required_date).sort()[0]||null,review:assessments.filter(a=>a.commitment&&!a.reviewed).length,fresh:assessments.filter(a=>a.fresh).length,case:state.cases.find(x=>x.supplier_id===supplier.id)};
}
function parseDate(raw){if(!raw)return null;let v=raw;const m=raw.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);if(m)v=`${m[3]}-${m[2]}-${m[1]}`;return validDate(v)?v:null;}
const DATE='(\\d{4}-\\d{2}-\\d{2}|\\d{2}\\.\\d{2}\\.\\d{4})';
export function extract(text,supplierId,state,manualLineId=null){
  const warnings=[],proposals=[];let refs=[...text.matchAll(/(?:\bPO|\bBestellung)\s*[:#]?\s*(\d{8,12})(?:\s*[,;/]?\s*(?:item|position|pos\.)\s*[:#]?\s*(\d+))?(?:\s*[,;/]?\s*(?:schedule(?:\s*line)?|einteilung)\s*[:#]?\s*(\d+))?/gi)];
  if(!refs.length){const l=manualLineId?state.lines.find(l=>l.id===manualLineId&&l.supplier_id===supplierId&&inScope(l,state)):null;if(!l)return {proposals,warnings:['No explicit purchase-order reference was found. Match the message manually before recording it.']};refs=[{0:'',1:l.po,2:l.item,3:l.schedule,index:0,manual:true}];warnings.push('This message is assigned by the buyer. Its original text contains no PO reference.');}
  for(let r=0;r<refs.length;r++){
    const ref=refs[r],body=text.slice(ref.index,refs[r+1]?.index??text.length);
    const candidates=state.lines.filter(x=>x.supplier_id===supplierId&&x.po===ref[1]&&(!ref[2]||Number(x.item)===Number(ref[2]))&&(!ref[3]||Number(x.schedule)===Number(ref[3]))&&inScope(x,state));
    if(candidates.length!==1){warnings.push(`PO ${ref[1]} could not be matched to one in-scope line for this supplier.`);continue;}
    const line=candidates[0];if(proposals.some(x=>x.line_id===line.id)){warnings.push(`Repeated references to ${line.po} require separate review. Nothing will be recorded automatically.`);continue;}
    const p={line_id:line.id,legs:[],dispatch:null,cause:null,recovery:null,next_update:null,uncertain:/uncertain|unconfirmed|not yet available|unsicher|unbestätigt|noch nicht/i.test(body),conflict:/unresolved conflict|still lists the original|widersprüch/i.test(body),reviewed:false,excerpts:{reference:ref[0]},match:ref.manual?'Buyer-confirmed manual assignment':ref[2]&&ref[3]?'Exact PO, item and schedule line':'Unique PO reference; buyer review required',needs_match_review:ref.manual||!(ref[2]&&ref[3])};
    const legPattern=new RegExp('(?:Delivery|Lieferung)\\s*:\\s*([0-9]+(?:[.,][0-9]{3})*)\\s*(PC|pcs|units|Stück|ST)\\s*(?:on|by|am|bis|zum)\\s*'+DATE,'gi');
    for(const m of body.matchAll(legPattern)){const date=parseDate(m[3]),qty=Number(m[1].replace(/[,.]/g,''));if(date&&Number.isSafeInteger(qty)&&qty>0){p.legs.push({qty,date,quote:m[0]});}else warnings.push(`Invalid delivery date or quantity in PO ${line.po}.`);}
    p.excerpts.legs=p.legs.map(x=>x.quote).join('\n');
    for(const [field,labels] of [['dispatch','Dispatch|Versand'],['next_update','Next update|Nächstes Update']]){const m=body.match(new RegExp('(?:'+labels+')\\s*:\\s*'+DATE,'i'));if(m){p[field]=parseDate(m[1]);if(p[field])p.excerpts[field]=m[0];else warnings.push(`Invalid ${field.replace('_',' ')} date in PO ${line.po}.`);}}
    for(const [field,labels] of [['cause','Cause|Grund|Ursache'],['recovery','Recovery|Maßnahme|Massnahme']]){const m=body.match(new RegExp('(?:'+labels+')\\s*:\\s*([^\\n]+)','i'));if(m){p[field]=m[1].trim().replace(/\.$/,'');p.excerpts[field]=m[0];}}
    const causeMap=[[/capacity|kapazität/i,'Capacity shortage'],[/material|materialmangel/i,'Material shortage'],[/quality|qualität/i,'Quality issue'],[/machine|maschinen/i,'Machine failure'],[/logistics|transport/i,'Logistics issue'],[/sub.supplier|vorlieferant/i,'Sub-supplier issue'],[/workforce|personal/i,'Workforce constraint'],[/customs|zoll/i,'Customs issue'],[/hold|zahlung/i,'Commercial hold'],[/force majeure|höhere gewalt/i,'Force majeure']];
    p.cause_category=p.cause?(causeMap.find(([rx])=>rx.test(p.cause))?.[1]||'Other'):'Cause not provided';
    if(!p.legs.length)warnings.push(`No supported explicit delivery quantity/date pair in PO ${line.po}. Missing fields stay unknown.`);
    proposals.push(p);
  }
  return {proposals,warnings};
}
export function initialize(seed){
  const state=structuredClone(seed);
  for(const l of state.lines){if(!l.seed_message)continue;const m=state.messages.find(x=>x.id===l.seed_message);const p=extract(m.body,l.supplier_id,state).proposals.find(x=>x.line_id===l.id);if(p)l.commitments.push({...p,id:'C-'+l.id,received:m.received,message_id:m.id,reviewed:l.seed_validated,reviewer:l.seed_validated?l.buyer:null,conflict:l.seed_conflict});delete l.seed_message;delete l.seed_validated;delete l.seed_conflict;}
  for(const c of state.cases){if(c.response_deadline){c.process='Awaiting supplier';state.requests.push({id:'REQ-'+c.id,case_id:c.id,supplier_id:c.supplier_id,status:'Awaiting supplier',created:addDays(state.as_of,-4)+'T10:00:00Z',deadline:c.response_deadline,subject:`[${c.id}] Delivery commitment clarification`,body:'Please confirm current delivery quantities and dates for the open schedule lines.',recipient:state.suppliers.find(s=>s.id===c.supplier_id).contact,approved_by:c.owner,lines:state.lines.filter(l=>l.case_id===c.id&&assess(l,state).status!=='On track').map(l=>l.id)});}}
  return state;
}
export function questionsFor(line,state){const a=assess(line,state),q=[];if(a.missing.length)q.push(...a.missing.map(s=>`Please confirm: ${s.charAt(0).toLowerCase()+s.slice(1)}.`));if(!a.fresh&&a.commitment)q.push('Please reconfirm whether the latest delivery quantities and dates still apply.');if(a.conflict)q.push('Please resolve the conflicting dates or quantities shown in your latest statement.');if(a.shortfall>0)q.push(`Please confirm how ${a.shortfall} ${line.uom} missing on ${line.required_date} will be recovered.`);if(!q.length)q.push(`Please reconfirm ${line.open_qty} ${line.uom} for delivery on ${line.required_date}.`);return q;}
export function draftRequest(supplier,lineIds,state,deadline){const selected=state.lines.filter(l=>l.supplier_id===supplier.id&&lineIds.includes(l.id));const c=state.cases.find(x=>x.supplier_id===supplier.id);return {subject:`[${c.id}] Delivery clarification | ${selected.length} schedule line${selected.length===1?'':'s'}`,body:`Hello ${supplier.name} delivery team,\n\nPlease provide the following delivery information by ${deadline}.\n\n`+selected.map(l=>`PO ${l.po}, item ${l.item}, schedule ${l.schedule}\n${l.description} (${l.material}) | ${l.open_qty} ${l.uom} required on ${l.required_date}\n`+questionsFor(l,state).map(q=>'- '+q).join('\n')).join('\n\n')+`\n\nFor each delivery, please use: Delivery: [quantity] PC on [YYYY-MM-DD].\nPlease distinguish each partial delivery and use arrival dates at the receiving plant.\n\nThis request is for delivery-status clarification only. It does not amend the underlying purchase order or constitute acceptance of revised delivery conditions.\n\nBest regards,\n${supplier.buyer}\nProcurement`};}
export function recordProposals(state,supplierId,text,received,result){
  if(!validDate(received.slice(0,10))||days(state.as_of,received)<0)throw Error('Use a received date on or before the snapshot date.');
  if(!result.proposals.length)throw Error('No matched commitment to record.');
  const mid='M-'+Date.now(),c=state.cases.find(x=>x.supplier_id===supplierId),supplier=state.suppliers.find(x=>x.id===supplierId);
  state.messages.push({id:mid,supplier_id:supplierId,subject:'Supplier reply | '+c.id,sender:supplier.contact,received,body:text,language:/Bestellung|Lieferung/.test(text)?'de':'en',kind:'supplier'});
  for(const p of result.proposals){const l=state.lines.find(x=>x.id===p.line_id);if(!l||l.supplier_id!==supplierId)throw Error('Supplier does not match.');l.commitments.push({...structuredClone(p),id:'C-'+Date.now()+'-'+l.id,message_id:mid,received,reviewed:false});}
  const answered=new Set(result.proposals.map(x=>x.line_id));
  for(const r of state.requests.filter(x=>x.case_id===c.id&&x.status==='Awaiting supplier')){r.answered_lines=[...new Set([...(r.answered_lines||[]),...r.lines.filter(x=>answered.has(x))])];if(r.lines.every(x=>r.answered_lines.includes(x)))r.status='Response received';}
  const waiting=state.requests.filter(x=>x.case_id===c.id&&x.status==='Awaiting supplier');
  c.process=waiting.length?'Awaiting supplier':'Response received';c.response_deadline=waiting.map(x=>x.deadline).sort()[0]||null;c.closed=false;c.next_action='Review extracted supplier commitments';
  return {message_id:mid,line_count:result.proposals.length};
}
export function metrics(state){const lines=state.lines.filter(l=>inScope(l,state)),a=lines.map(l=>assess(l,state));return {lines:lines.length,attention:a.filter(x=>!['On track','Resolved'].includes(x.status)).length,fresh:a.filter(x=>x.fresh).length,coverage:lines.length?Math.round(100*a.filter(x=>x.fresh).length/lines.length):0,shortfall:a.filter(x=>x.status==='Confirmed shortfall').length,unknown:a.filter(x=>x.status==='Unknown').length,review:a.filter(x=>x.commitment&&!x.reviewed).length,overdue:state.requests.filter(r=>r.status==='Awaiting supplier'&&r.deadline<state.as_of).length,assessments:a};}
export function csvExport(state){const fields=['Supplier','PO','Item','Schedule line','Material','Plant','Required date','Open quantity','UOM','SAP date','SAP quantity','Supplier deliveries','Quantity covered on time','Confirmed gap on required date','Delivery assessment','Information status','Buyer validated','Source message','Evidence received'];const rows=state.lines.filter(l=>inScope(l,state)).map(l=>{const a=assess(l,state),c=a.commitment;return [state.suppliers.find(s=>s.id===l.supplier_id).name,l.po,l.item,l.schedule,l.material,l.plant,l.required_date,l.open_qty,l.uom,l.sap_date,l.sap_qty??'',c?.legs.map(x=>`${x.qty} ${l.uom} on ${x.date}`).join('; ')||'Unknown',c?.legs.length?a.onTime:'',a.shortfall??'',a.status,a.information,c?.reviewed?'Yes':'No',c?.message_id||'',c?.received||''];});const quote=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replaceAll('"','""')+'"';return '\ufeff'+[fields,...rows].map(row=>row.map(quote).join(',')).join('\r\n');}
