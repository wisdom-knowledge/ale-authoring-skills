"""Validate a Rubric result for the web host; signing belongs to the host."""
import argparse
import json
from pathlib import Path
from check_rubric import validate_contract, check_files


def export(rows, reply):
    validate_contract(rows)
    if len(rows) > 100 or not reply.strip() or len(reply) > 30000:
        raise ValueError('Invalid result size or reply')
    for row in rows:
        if len(row['id']) > 40 or len(row['description']) > 2000:
            raise ValueError('Rubric exceeds web contract limits')
    return {'schema': 'ale-rubric-result/v1', 'reply': reply, 'rubrics': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rubric', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--reply', required=True)
    parser.add_argument('--review', type=Path, required=True)
    args = parser.parse_args()
    report = check_files(args.rubric, args.review)
    if report['status'] != 'PASS_DRAFT':
        raise ValueError('Rubric preflight is not PASS_DRAFT; preserve the draft and report the blocker')
    value = export(json.loads(args.rubric.read_text(encoding='utf-8-sig')), args.reply)
    with args.output.open('x', encoding='utf-8') as target:
        json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')


if __name__ == '__main__':
    main()
