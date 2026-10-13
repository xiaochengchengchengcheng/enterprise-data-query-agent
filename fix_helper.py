# -*- coding: utf-8 -*-
"""One-shot cleanup: align _json_default with the task spec."""
import io

path = r'llm_gateway.py'
with io.open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
i = 0
n = len(lines)
while i < n:
    line = lines[i]

    # 1) Add datetime/date import right after the Decimal import, if not present.
    if line.rstrip('\r\n') == 'from decimal import Decimal':
        out.append(line)
        # peek next non-blank to avoid duplicate
        j = i + 1
        while j < n and lines[j].strip() == '':
            j += 1
        if j < n and lines[j].rstrip('\r\n') == 'from datetime import datetime, date':
            pass  # already present later; will be handled when reached
        else:
            out.append('from datetime import datetime, date\n')
        i += 1
        continue

    # 2) Replace the helper block (comment + def ... raise) with spec-aligned version.
    if line.rstrip('\r\n') == '# JSON序列化辅助函数：处理Decimal等非标准JSON类型':
        # skip through the closing 'raise TypeError(...)' line
        while i < n and not lines[i].lstrip().startswith('raise TypeError'):
            i += 1
        # skip the raise line itself
        if i < n:
            i += 1
        # emit the spec-aligned helper
        out.append('\n')
        out.append('def _json_default(obj):\n')
        out.append('    """JSON序列化辅助函数，处理Decimal/date/datetime等非标准类型。"""\n')
        out.append('    if isinstance(obj, Decimal):\n')
        out.append('        return float(obj)\n')
        out.append('    if isinstance(obj, (date, datetime)):\n')
        out.append('        return str(obj)\n')
        out.append('    raise TypeError(f\'Object of type {type(obj).__name__} is not JSON serializable\')\n')
        continue

    out.append(line)
    i += 1

# Collapse 3+ consecutive blank lines into 2, to keep PEP8 spacing.
text = ''.join(out)
import re as _re
text = _re.sub(r'\n{3,}', '\n\n\n', text)

with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

print('done')
