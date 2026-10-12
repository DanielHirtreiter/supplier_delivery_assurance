"""Create reproducible, fictional supplier cases. Python standard library only."""
import json
from datetime import date, timedelta
from pathlib import Path

BASE = date(2026, 9, 7)
def day(offset):
    return (BASE + timedelta(days=offset)).isoformat()

def create_seed():
    names = [
        ('S1001','Nordwerk Components','DE','Munich','Anna Weber','NC','Machine failure'),
        ('S1002','Rheinwerk Precision','DE','Stuttgart','Anna Weber','RP','Capacity shortage'),
        ('S1003','Hansa Electronics','DE','Munich','Jonas Keller','HE','Material shortage'),
        ('S1004','Alpin Polymers','AT','Stuttgart','Anna Weber','AP','Cause not provided'),
        ('S1005','Vektor Motion','CZ','Munich','Jonas Keller','VM','Quality issue'),
        ('S1006','Bergmann Metals','DE','Stuttgart','Anna Weber','BM','Logistics issue'),
        ('S1007','Elbe Packaging','DE','Munich','Jonas Keller','EP','Cause not provided'),
        ('S1008','Küstenlager Bearings','DE','Stuttgart','Jonas Keller','KB','Cause not provided'),
    ]
    materials = [('C-4711','Drive control module'),('M-2204','Precision housing'),('E-3100','Sensor assembly'),('P-8042','Polymer seal kit'),('M-6021','Servo coupling'),('M-7020','Mounting bracket'),('P-9008','Transit packaging'),('M-5106','Bearing cartridge')]
    offsets = [[4,18,39,74],[7,25,47,80],[10,31,54,66],[15,36,59,79],[3,23,44,72],[12,33,57,82],[17,38,61,76],[20,40,63,83]]
    kinds = [['split','late','good','good'],['uncertain','missing','stale','good'],['partial','good','stale','good'],['good']*4,['conflict','late','good','good'],['stale','good','good','good'],['good','good','good','good'],['missing','uncertain','good','good']]
    suppliers, lines, messages, cases = [], [], [], []
    for i,(sid,name,country,plant,buyer,initials,cause) in enumerate(names):
        suppliers.append(dict(id=sid,name=name,country=country,plant=plant,buyer=buyer,initials=initials,contact=f'delivery@{sid.lower()}.example',language='de' if i in (1,4) else 'en'))
        case_id=f'DA-{1001+i}'
        cases.append(dict(id=case_id,supplier_id=sid,owner=buyer,process='Needs buyer review' if i in (0,1,2,4,7) else 'Monitoring',closed=False,next_action='Validate supplier evidence' if i in (0,2,4) else 'Clarify missing commitments' if i in (1,7) else 'Monitor next delivery',response_deadline=day(-1) if i in (1,7) else None,history=[dict(at=day(0)+'T08:00:00Z',action='Synthetic SAP snapshot imported',detail='Required dates and SAP confirmations preserved separately.')]))
        for j,offset in enumerate(offsets[i]):
            lid=f'L{i+1}{j+1}'
            qty=1200 if i==0 and j==0 else [800,1000,600,400][(i+j)%4]
            kind=kinds[i][j];po=f'45000{12001+i*11+j}'
            line=dict(id=lid,case_id=case_id,supplier_id=sid,po=po,item='10',schedule='1',material=materials[i][0],description=materials[i][1],plant=plant,buyer=buyer,required_date=day(offset),ordered_qty=qty+200,received_qty=200,open_qty=qty,uom='PC',sap_date=day(offset),sap_qty=None if kind=='missing' else qty,deleted=False,finally_delivered=False,manual_flag=False,commitments=[])
            lines.append(line)
            if kind=='missing': continue
            age=22 if kind=='stale' else 0 if offset<28 else 2
            received=day(-age)+'T07:45:00Z'
            legs=[dict(qty=qty,date=day(offset))]
            if kind=='split':legs=[dict(qty=720,date=day(offset)),dict(qty=480,date=day(offset+10))]
            if kind=='late':legs=[dict(qty=qty,date=day(offset+7))]
            if kind=='partial':legs=[dict(qty=360,date=day(offset))]
            if kind=='conflict':legs=[dict(qty=qty,date=day(offset+6))]
            if kind=='uncertain':legs=[]
            commitment_lines='\n'.join(f'Delivery: {x["qty"]} PC on {x["date"]}.' for x in legs)
            if kind=='uncertain':commitment_lines='Delivery timing remains uncertain. A firm date and quantity are not yet available.'
            adverse=kind in ('split','late','partial','conflict','uncertain')
            recovery='Additional production shift planned.' if adverse and kind!='partial' else None
            text=f'Hello {buyer.split()[0]},\n\nPO {po}, item 10, schedule 1.\n{commitment_lines}\n'
            if legs:text+=f'Dispatch: {day(offset-2)}.\n'
            if adverse:text+=f'Cause: {cause}.\n'
            if recovery:text+=f'Recovery: {recovery}\n'
            if kind not in ('partial','uncertain'):text+=f'Next update: {day(min(offset,2))}.\n'
            if kind=='conflict':text+='Our shipping desk still lists the original date. Please verify the two commitments.\n'
            text+=f'\nRegards,\n{name} delivery team'
            mid=f'M-{lid}'
            messages.append(dict(id=mid,supplier_id=sid,line_id=lid,subject=f'Delivery update | PO {po}',sender=f'delivery@{sid.lower()}.example',received=received,body=text,language='en',attachment=None,kind='supplier'))
            line['seed_message']=mid
            line['seed_validated']=kind=='good'
            line['seed_conflict']=kind=='conflict'
    return dict(schema_version=1,as_of=day(0),settings=dict(horizon=84,near_business_days=3,mid_calendar_days=7,far_calendar_days=14),suppliers=suppliers,lines=lines,messages=messages,cases=cases,requests=[],audit=[dict(at=day(0)+'T08:00:00Z',action='Demo dataset created',detail='8 fictional suppliers · 32 open schedule lines · 2 plants')])

if __name__=='__main__':
    path=Path(__file__).parent/'dist'/'seed.json'
    path.write_text(json.dumps(create_seed(),ensure_ascii=False,indent=2)+'\n')
    print(f'Created {path.name}: 8 suppliers, 32 schedule lines')
