import logging
import yaml
import json
import coloredlogs
import pandas as pd

ip_mode = False
dynamic_flink_url = False
prom = None
flink_base_url = "http://flink.127-0-0-1.sslip.io:30080"
zeppelin_base_url = "http://zeppelin.127-0-0-1.sslip.io:30080"
prometheus_base_url = "http://admin:prom-operator@prometheus.127-0-0-1.sslip.io:30080"
kafka_bridge_base_url = "http://kafka.127-0-0-1.sslip.io:30080"
datagen_flink_base_url = "http://datagen-flink.127-0-0-1.sslip.io:30080"


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def setup_logging(default_path=None, default_level=logging.INFO):
    if default_path is not None:
        with open(default_path, 'rt') as f:
            try:
                config = yaml.safe_load(f.read())
                logging.config.dictConfig(config)
                coloredlogs.install(level=default_level)
            except Exception as e:
                print(e)
                print('Error in Logging Configuration. Using default configs')
                logging.basicConfig(level=default_level)
                coloredlogs.install(level=default_level)        
    logger = logging.getLogger("streambed")

    return logger

def read_results(path):
    df = pd.read_csv(path, sep=";", header=None, names=["params_datagen_run", "task_parallelism", "job_id", "cpu", "memory", "task_managers_qty", "run", "start_time", "duration", "task_slots_per_task_manager", "source_parallelism", "parallelism", "evenly_spread", "task_slots_limit", "observed_source_rate", "objective"])
    df_params = pd.json_normalize(df["params_datagen_run"].str.replace("'","\"").apply(json.loads))
    df = pd.concat([df_params, df], axis=1)

    def get_title(string):
        return string.str.split(";")

    def first_element(arr):
        #print(arr.values)
        return arr.values[0][0]
    def second_element(arr):
        if isinstance(arr, float):
            return 1
        else:
            return arr.split(";")[1]

    test = df["task_parallelism"].str.split("|", expand=True).iloc[[1]]
    columns = test.apply(get_title).apply(first_element).values
    #display(test)
    test = df["task_parallelism"].str.split("|", expand=True).applymap(second_element)
    test.columns = columns

    df =pd.concat([df,  test.add_prefix("query.").astype(int)], axis=1)
    df["params.TPS"] = df["params.TPS"].astype(int)
    df["used_task_slots"] = df.filter(regex="query\..*").sum(axis=1)
    df["task_slot_memory"] = df["memory"] / df["task_slots_per_task_manager"]
    
    return (df, columns)
