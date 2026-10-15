from catmeal.screenrecording import parse_camera_clock,clock_transitions,group_contact_samples

def test_clock_uses_camera_date_and_timezone():
 assert parse_camera_clock('mi 2026/10/03 08:10:49') == 1790986249
 assert parse_camera_clock('2026/13/03 08:10:49') is None
 assert parse_camera_clock('paused') is None

def test_freezes_rewinds_and_missing_are_not_observation_duration():
 rows=[dict(id=i,camera_timestamp=v) for i,v in enumerate([100,106,106,99,200,None])]
 assert [r['kind'] for r in clock_transitions(rows)]==['advance','repeat','rewind','jump','unreadable']

def test_identity_and_real_time_gap_grouping():
 def r(i,t,cat='orange',seg=0):return dict(id=i,camera_timestamp=t,cat_id=cat,segment=seg)
 groups=group_contact_samples([r(0,100),r(1,100),r(2,110),r(3,100,'gray'),r(4,171),r(5,172,seg=1)])
 assert sorted(len(g) for g in groups)==[1,1,1,2]
