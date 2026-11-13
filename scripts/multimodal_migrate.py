"""Stopped-app backup-first activation; defaults to read-only dry run."""
import argparse
import json
from personal_learning_assistant.services.multimodal_schema import activate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',required=True);p.add_argument('--library-root',required=True)
    p.add_argument('--apply',action='store_true',help='Stop ANVAYA and all writers before applying')
    args=p.parse_args()
    print(json.dumps(activate(args.database,args.library_root,apply=args.apply),default=str))

if __name__=='__main__':main()
