import sqlite3, os, sys
sys.path.insert(0, 'src')
db = 'data/research_agent.db'
print('prod_db_bytes', os.path.getsize(db))
print('prod_db_mtime', os.path.getmtime(db))
con = sqlite3.connect('file:' + db + '?mode=ro', uri=True)
cur = con.cursor()
print('portals', cur.execute('select count(*) from portals').fetchone())
print('scan_enabled', cur.execute('select count(*) from portals where scan_enabled=1').fetchone())
print('runs', cur.execute('select count(*) from scan_runs').fetchone())
print('jobs', cur.execute('select count(*) from source_jobs').fetchone())
print('analyses', cur.execute('select count(*) from job_analyses').fetchone() if any(r[0]=='job_analyses' for r in cur.execute("select name from sqlite_master where type='table'")) else ('no_table',))
import json
from research_agent.sources.ats.workday import WorkdayAdapter
from research_agent.sources.ats.registry import default_adapter_registry
from research_agent.sources.base import PortalTarget
ad = WorkdayAdapter()
reg = default_adapter_registry()
rows = cur.execute('select id,host,normalized_jobs_url,jobs_search_url,health_state,access_state,ats_families_json,ats_confidences_json from portals where scan_enabled=1 order by id').fetchall()
served = []
for pid, host, nurl, url, health, access, famj, confj in rows:
    t = PortalTarget(portal_id=pid, jobs_search_url=url, normalized_jobs_url=nurl, host=host, ats_families=tuple(json.loads(famj)), ats_confidences=tuple(json.loads(confj)))
    try:
        s = ad.supports(t)
    except Exception as e:
        s = 'ERR %s' % e
    sel = reg.select(t)
    selname = type(sel).__name__ if sel else 'none'
    if s is True:
        served.append((pid, host, url, health, access, famj, selname))
        print('SERVED', pid, host, url, health, access, famj, '->', selname)
print('served_count', len(served))
con.close()
