"""Validate a confirmed authoring draft and emit the host JSON response."""
import argparse
import json
import math
from pathlib import Path


def validate(draft):
    if not isinstance(draft, dict):
        raise ValueError('draft must be an object')
    limits = {'title': 120, 'softwareVersion': 200, 'description': 12000,
              'prompt': 30000, 'economicValue': 10000, 'steps': 10000}
    allowed = set(limits) | {'software', 'criteria', 'rubrics', 'system', 'domain'}
    if set(draft) - allowed:
        raise ValueError('unexpected draft fields')
    for key, maximum in limits.items():
        value = draft.get(key)
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError(f'invalid {key}')
    for key in ['prompt', 'economicValue', 'steps']:
        if not draft[key].strip():
            raise ValueError(f'{key} is required')
    software = draft.get('software')
    if not isinstance(software, list) or not 1 <= len(software) <= 20 or any(not isinstance(s, str) or not 1 <= len(s) <= 80 for s in software):
        raise ValueError('invalid software')
    for key, maximum in [('system', 80), ('domain', 200)]:
        if key in draft and (not isinstance(draft[key], str) or len(draft[key]) > maximum):
            raise ValueError(f'invalid {key}')
    for field in ['criteria', 'rubrics']:
        items = draft.get(field)
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError(f'invalid {field}')
        ids = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {'id', 'requirement', 'evidence', 'method', 'hardGate', 'weight'}:
                raise ValueError('invalid criterion fields')
            for key, maximum in [('id', 40), ('requirement', 2000), ('evidence', 1000), ('method', 1000)]:
                if not isinstance(item[key], str) or len(item[key]) > maximum or key == 'id' and not item[key]:
                    raise ValueError(f'invalid criterion {key}')
            if item['id'] in ids:
                raise ValueError('duplicate criterion id')
            ids.add(item['id'])
            weight = item['weight']
            if type(item['hardGate']) is not bool or type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 100:
                raise ValueError('invalid criterion weight or hardGate')
    return draft


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('draft', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--reply', required=True)
    args = parser.parse_args()
    if args.draft.resolve() == args.output.resolve():
        parser.error('output must differ from source draft')
    if not args.reply.strip() or len(args.reply) > 30000:
        parser.error('reply is required and must be at most 30000 characters')
    draft = validate(json.loads(args.draft.read_text(encoding='utf-8-sig')))
    # The trusted web server adds identity, version and signature after validation.
    response = {'reply': args.reply, 'draft': draft}
    with args.output.open('x', encoding='utf-8') as target:
        json.dump(response, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')


if __name__ == '__main__':
    main()
