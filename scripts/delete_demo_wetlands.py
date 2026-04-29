import re
from mapping.models import Wetland

pattern = re.compile(r'(?i)^wetland\s*\d+$')
all_wetlands = Wetland.objects.all()
matches = [w for w in all_wetlands if w.name and pattern.match(w.name)]
print('Found', len(matches), 'demo wetlands:', [w.id for w in matches])
if matches:
    ids = [w.id for w in matches]
    Wetland.objects.filter(id__in=ids).delete()
    print('Deleted', len(ids), 'records')
else:
    print('No demo wetlands found')

remaining = [w for w in Wetland.objects.all() if w.name and pattern.match(w.name)]
print('Remaining', len(remaining))
