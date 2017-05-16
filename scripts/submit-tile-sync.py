#!/usr/bin/env python


import time
from pathlib import Path
from subprocess import check_output
from typing import Mapping

SUBMIT_THROTTLE_SECS = 1


def main(name: str, folder: Path, submit_limit: int, concurrent_jobs=4):
    folder = folder.absolute()

    run_directory = Path('runs').absolute()

    if not folder.exists():
        raise ValueError("Folder doesn't exist: %s" % folder)

    # For input folder, get list of unique tile X values
    # They are named "X_Y", eg "-12_23"
    tile_xs = set(int(p.name.split('_')[0]) for p in folder.iterdir() if p.name != 'ncml')
    tile_xs = sorted(tile_xs)

    print("Found %s total jobs" % len(tile_xs))

    # To maintain concurrent_jobs limit, we set a pbs dependency on previous jobs.

    # mapping of slot number to the last job id to be submitted in it.
    # type: Mapping[int, str]
    last_job_slots = {}

    for i, tile_x in enumerate(tile_xs):
        if i == submit_limit:
            print("Submit limit ({}) reached, done.".format(submit_limit))
            break

        subjob_name = '{}_{}'.format(name, tile_x)

        output_path = run_directory.joinpath('{}.tsv'.format(subjob_name))
        error_path = run_directory.joinpath('{}.log'.format(subjob_name))

        if output_path.exists():
            print("[{}] {}: output exists, skipping".format(i, subjob_name))
            continue

        last_job_id = last_job_slots.get(i % concurrent_jobs)

        input_folders = list(folder.glob('{}_*'.format(tile_x)))

        job_id = submit_job(error_path, input_folders, output_path, subjob_name, require_job_id=last_job_id)
        print("[{}] {}: submitted {}".format(i, subjob_name, job_id))
        last_job_slots[i % concurrent_jobs] = job_id

        time.sleep(SUBMIT_THROTTLE_SECS)


def submit_job(error_path, input_folders, output_path, subjob_name, require_job_id=None):
    requirements = []
    if require_job_id:
        requirements.extend(['-W', 'depend=afterok:{}'.format(str(require_job_id).strip())])

    sync_command = [
        'python', '-m', 'datacubenci.sync', '-j', '4',  # '--trash-missing', '--trash-archived',
        # glob all the paths starting with X_
        *(map(str, input_folders))
    ]
    output = check_output([
        'qsub', '-V',
        '-P', 'v10',
        '-q', 'express',
        '-l', 'walltime=20:00:00,mem=4GB,ncpus=2,jobfs=1GB,other=gdata',
        '-l', 'wd',
        '-N', 'sync-{}'.format(subjob_name),
        '-m', 'e',
        '-M', 'jeremy.hooke@ga.gov.au',
        '-e', str(error_path),
        '-o', str(output_path),
        *requirements,
        '--',
        *sync_command
    ])
    job_id = output.decode('utf-8').strip(' \\n')
    return job_id


if __name__ == '__main__':
    main('5fc', Path('/g/data/fk4/datacube/002/LS5_TM_FC'), 4)