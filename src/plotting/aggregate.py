#!/usr/bin/env python3
"""
This script expects the `quees` dir as its argument.
The structure should be as follow.

```
$ tree queues/

queues/
├── queue-0
│   ├── id:000000,time:0,orig:dummy
│   ├── id:000001,src:000000,time:601,op:havoc,rep:8,+cov
│   ├── ...
│   └── id:000265,src:000251,time:64221476,op:havoc,rep:16
└── queue-1
│   ├── id:000000,time:0,orig:dummy
│   ├── id:000001,src:000000,time:601,op:havoc,rep:8,+cov
│   ├── ...
│   └── id:000265,src:000251,time:64221476,op:havoc,rep:16
└── queue-2
└── ...
└── queue-n
```

Each of the files in the `queue-n` dirs should have the format
<bitmap_id>:<hit_count>[\n<bitmap_id>:<hit_count>]+

For example
```
655063:1
1168669:1
1181216:2
```

"""
import sys
import os
import logging
import pandas as pd


################################################################################
# set up logging
################################################################################
FORMAT = "%(asctime)s,%(msecs)d %(levelname)-8s " \
         "[%(filename)s:%(lineno)d] %(message)s"
logging.basicConfig(format=FORMAT,
                    datefmt='%Y-%m-%d:%H:%M:%S',
                    level=logging.DEBUG)
log = logging.getLogger(__name__)

################################################################################
# start script
################################################################################

def resample(data):
    """ resampling coverage measurments of several experiments to align
        timestamps """
    data = data.reindex(range(0, 86401, 1800), method="ffill")
    last_row = data.iloc[-1:]
    data.drop_duplicates(keep='first', inplace=True)
    data = pd.concat([data, last_row], axis=0)
    return data


def handle_qdir(qdir: str):
    """ Handle one qdir. """

    hitmap_files = [os.path.join(qdir, hitmap_file)
                    for hitmap_file in os.listdir(qdir)]

    time_to_edgecnt = dict()

    seen_bitmap_ids = set()
    # we use this list to sort all files according to their time
    hf_to_time = []
    for hf in hitmap_files:
        if not os.path.isfile(hf):
            log.error(f"{hf} is not a file")
            sys.exit(-1)
        hf_name = os.path.basename(hf)
        tmp_attrs = [attrs.split(":") for attrs in hf_name.split(",")]
        name_attrs = {attr[0]: attr[1] for attr in tmp_attrs if len(attr) == 2}

        if "time" not in name_attrs.keys():
            log.error(f"filename of {hf} is malformed. `time` is missing.")
            sys.exit(-1)

        t = int(name_attrs["time"]) / 1000

        hf_to_time.append((hf, t))

    hf_to_time.sort(key=lambda x: x[1])
    # now we can open the bitmap files sorted by time
    # this will ensure that we add new edges in order
    for hf in hf_to_time:

        with open(hf[0]) as f:
            while True:
                line = f.readline()
                if not line:
                    break
                # by adding the bitmap ids here we imply that the files
                # are opened in sorted order in time
                seen_bitmap_ids.add(line.split(":")[0])
        time_to_edgecnt[hf[1]] = len(seen_bitmap_ids)

    return time_to_edgecnt


def aggregate_raw_queues(queues_dir: str):
    if not os.path.isdir(queues_dir):
        log.error(f"{queues_dir} is not a directory")
        sys.exit(-1)

    log.info(f"Looking for queues in {queues_dir}.")

    queues_dir = os.path.normpath(queues_dir)
    queue_dirs = [os.path.join(queues_dir, qdir)
                  for qdir in os.listdir(queues_dir)]

    # sanity check for `queue-n` dirs
    for qdir in queue_dirs:
        if not os.path.isdir(qdir):
            log.error(f"{qdir} is not a directory")
            sys.exit(-1)

    time_to_edgecnt_by_q = dict()
    for qdir in queue_dirs:
        time_to_edgecnt = handle_qdir(qdir)
        time_to_edgecnt_by_q[os.path.basename(qdir)] = time_to_edgecnt

    return time_to_edgecnt_by_q


def main(queues_dir: str, out_path: str):

    time_to_edgecnt_by_q = aggregate_raw_queues(queues_dir)

    agg_df = None
    for q, data in time_to_edgecnt_by_q.items():
        df = pd.DataFrame.from_dict(data, orient="index")
        df.sort_index(inplace=True)
        resampled_df = resample(df)
        resampled_df.rename(columns={0: q}, inplace=True)
        if agg_df is None:
            agg_df = resampled_df
            agg_df.index.name = "time"
        else:
            agg_df = agg_df.join(resampled_df)

    # get max edge coverage
    max_cov_seen = agg_df.max().max()
    agg_df = agg_df.ffill()
    # agg_df.index = agg_df.index.astype('int64') // 10**9
    mean_df = agg_df.mean(axis=1)# / (max_cov_seen * 1.1)
    mean_df.name = "avg"
    min_df = agg_df.min(axis=1)# / (max_cov_seen * 1.1)
    min_df.name = "min"
    max_df = agg_df.max(axis=1)# / (max_cov_seen * 1.1)
    max_df.name = "max"
    std_df = agg_df.std(axis=1)# / (max_cov_seen * 1.1)
    std_df.name = "std"
    agg_df = agg_df.join(max_df)
    agg_df = agg_df.join(min_df)
    agg_df = agg_df.join(mean_df)
    agg_df = agg_df.join(std_df)
    agg_df.to_csv(out_path, sep=",", float_format='%11.2f')


def usage():
    print(f"{sys.argv[0]} /dir/containing/queue-dirs /path/to/out.csv")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        usage()
        sys.exit(0)

    main(sys.argv[1], sys.argv[2])
