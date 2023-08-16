from unittest import result
import time 
import requests 
import os 
from tqdm.auto import tqdm
import datetime
import csv
from time import sleep
import copy
from statistics import mean 
import json

import logging

from common_alloc import *
from common_flink import *
from common_k8s import *
from model import *
import common
logger = logging.getLogger('streambed')

default_raw_queries = {
    "flink_taskmanager_job_task_numRecordsIn": 'flink_taskmanager_job_task_numRecordsIn{{job_id=~"{job_id}"}}',
    "flink_taskmanager_job_task_numRecordsOut": 'flink_taskmanager_job_task_numRecordsOut{{job_id=~"{job_id}"}}',
    "flink_taskmanager_job_task_busyTimeMsPerSecond": 'flink_taskmanager_job_task_busyTimeMsPerSecond{{job_id=~"{job_id}"}}',
    "flink_taskmanager_job_task_backPressuredTimeMsPerSecond": 'flink_taskmanager_job_task_backPressuredTimeMsPerSecond{{job_id=~"{job_id}"}}',
    "flink_taskmanager_job_task_idleTimeMsPerSecond": 'flink_taskmanager_job_task_backPressuredTimeMsPerSecond{{job_id=~"{job_id}"}}',
    "flink_taskmanager_job_task_operator_pendingRecords": 'flink_taskmanager_job_task_operator_pendingRecords{{job_id=~"{job_id}"}}',
    "container_cpu_usage_seconds_total": 'container_cpu_usage_seconds_total{{container=~"taskmanager|kafka"}}',
    "container_memory_usage_bytes": 'container_memory_usage_bytes{{container="taskmanager|kafka"}}',
}

default_agg_queries = {
    "rate_out_sum": 'sum by (task_name, task_id) (irate(flink_taskmanager_job_task_numRecordsOut{{job_id="{job_id}"}}[15s]))',
    "rate_in_sum": 'sum by (task_name, task_id) (irate(flink_taskmanager_job_task_numRecordsIn{{job_id="{job_id}"}}[15s]))',
    "idle_time_avg": 'avg by (task_name, task_id) (flink_taskmanager_job_task_idleTimeMsPerSecond{{job_id=~"{job_id}"}})',
    "bp_time_avg": 'avg by (task_name, task_id) (flink_taskmanager_job_task_backPressuredTimeMsPerSecond{{job_id=~"{job_id}"}})',
    "busy_time_avg": 'avg by (task_name, task_id) (flink_taskmanager_job_task_busyTimeMsPerSecond{{job_id=~"{job_id}"}})',
    "cpu_tm_rate": 'irate(container_cpu_usage_seconds_total{{container="taskmanager"}}[60s])',
    "cpu_kafka_rate": 'irate(container_cpu_usage_seconds_total{{container="kafka"}}[60s])',
    }

def reset_interpreters(base_url=None):
    if base_url is None:
        base_url = common.zeppelin_base_url
    r = requests.put(base_url + "/api/interpreter/setting/restart/flink", json={})
    logger.debug("Reset interpreters: {}".format(r.status_code))

def reset_interpreter(interpreter, base_url=None):
    if base_url is None:
        base_url = common.zeppelin_base_url
    r = requests.put(base_url + "/api/interpreter/setting/restart/" + interpreter)
    return r.status_code

def get_throughput_source(job_id, min_date, max_date, rampup=30, step="5s"):
    df_detailed_run = prom_query_range(request_source_througput.format(job_id), min_date, max_date, step)
    return df_detailed_run[df_detailed_run.second > rampup]

def launch_job_async(notebook="/xp_intro", params_query=None, params_datagen=None, timeout=None, cancel=True):
    r = requests.get(common.zeppelin_base_url + "/api/notebook")
    note_id = None
    for element in r.json()["body"]:
        if element["path"] == notebook:
            note_id = element["id"]
            break
    #print ("Stop notebook " + note_id)
    r = requests.delete(common.zeppelin_base_url + "/api/notebook/job/" + note_id)
    #print ("Clear notebook " + note_id)
    r = requests.put(common.zeppelin_base_url + "/api/notebook/" + note_id + "/clear")

    paragraphs = requests.get(common.zeppelin_base_url + "/api/notebook/"+ note_id).json()["body"]["paragraphs"]
    error = False
    for paragraph in paragraphs:
        if paragraph["config"]["enabled"]:
            #if "title" in paragraph:
            #    print(paragraph["title"], end="")
            #else:
            #    print(paragraph["text"].split("\n")[0], end="")
            paragraph_id = paragraph["id"]
            if "title" in paragraph and (paragraph["title"] == "Datagen tables creation" or paragraph["title"] == "Kafka table creation"):
                result_paragraph = requests.post(common.zeppelin_base_url + "/api/notebook/job/" + note_id + "/" + paragraph_id, json=params_datagen)
            elif "title" in paragraph and paragraph["title"] == "Query":
                result_paragraph = requests.post(common.zeppelin_base_url + "/api/notebook/job/" + note_id + "/" + paragraph_id, json=params_query)
            else:
                result_paragraph = requests.post(common.zeppelin_base_url + "/api/notebook/job/" + note_id + "/" + paragraph_id)

            start = time.time()
            is_timeout = False
            finished = False
            while not finished:
                if "title" in paragraph and paragraph["title"] == "Query":
                    return                
                status_paragraph = requests.get(common.zeppelin_base_url + "/api/notebook/job/"+ note_id + "/" + paragraph_id)
                status = status_paragraph.json()["body"]["status"]
                if status != "RUNNING" and status != "PENDING" and status_paragraph.status_code == 200:
                    #print(status_paragraph.json()["body"]["status"], end = "")

                    finished = True
                    break

                now = time.time()
                if (is_timeout is not None) and start + timeout < now:
                    is_timeout = True
                    break

                #print(".", end="")
                time.sleep(1)

            if finished: 
                pass
                #print(" [" + bcolors.OKGREEN + "OK" + bcolors.ENDC + "]")
            elif is_timeout:
                pass
                #print(" [" + bcolors.WARNING + "OK" + bcolors.ENDC + "]")
            else:
                #print(" [" + bcolors.FAIL + "Error" + bcolors.ENDC + "]")
                logger.error("Fail on notebook: " + result_paragraph.text)
                error = True
                break

    if error:
        logger.error("Job {} failed".format(notebook))
    else:
        logger.debug("Job finished")

    query_paragraph = None
    for paragraph in paragraphs:
        if "title" in paragraph and paragraph["title"] == "Query":
            query_paragraph = paragraph
            break
            
    r = requests.get(common.zeppelin_base_url + "/api/notebook")
    note_id = None
    for element in r.json()["body"]:
        if element["path"] == notebook:
            note_id = element["id"]
            break
    job_id = None
    if query_paragraph is not None: 
        r = requests.get(common.zeppelin_base_url + "/api/notebook/{}/paragraph/{}".format(note_id, query_paragraph["id"]))
        job_id = r.json()["body"]["runtimeInfos"]["jobUrl"]["values"][0]["jobUrl"].split("/")[-1]

    if is_timeout and cancel and job_id is not None:
        logger.debug("Canceling job {}".format(job_id))
        cancel_job(job_id)
    return (job_id, paragraphs, )
def inject_kafka(job_name, throughput, events_qty, sink_qty=16, timeout=600, base_url=None, notebook="/xp_datagen"):
    if base_url is None:
        base_url = common.datagen_flink_base_url
    throughput = int(throughput / sink_qty) 
    params_datagen = { 
        "params": {
            "TPS": str(throughput),
            "EVENTS_NUM": str(events_qty),
            "PERSON_PROPORTION": str(1),
            "AUCTION_PROPORTION": str(3),
            "BID_PROPORTION": str(46),
            "NEXMARK_TABLE": "kafka", # datagen or kafka
            "TOPIC": "nexmark-datagen",
            "BOOTSTRAP_SERVERS": "my-cluster-kafka-bootstrap.kafka:9092",
        },
        "notebook": notebook,
        "timeout": timeout,
    }

    params_query = { "params": {
        "SOURCES": str(sink_qty), 
        "PARALLELISM" : str(sink_qty), 
        "TASK_PARALLELISM": "", 
        "JOB_NAME": job_name} }
    #params_query = {"params": {"JOB_NAME": job_name}}
    launch_job_async(notebook=params_datagen["notebook"], params_datagen=params_datagen, params_query=params_query, timeout=params_datagen["timeout"])
    sleep(60)
    datagen_job_id = get_jobid_by_name(job_name, base_url=base_url)[0]

    # wait for the end of the 
    (start_time, duration, job) = get_job_info(datagen_job_id, base_url=base_url)
    while (duration < params_datagen["timeout"] * 1000) and (job["state"] == "RUNNING"):
        sleep(5)
        (start_time, duration, job) = get_job_info(datagen_job_id, base_url=base_url)
    return datagen_job_id


def change_rate(job_id, howmuch, when=None, nb_sources=5):
    if when is None:
        timestamp = None
    else:
        timestamp = int(time.time() * 1000) + (1000 * when)

    if howmuch is None:
        message = None
    else:
        if timestamp is None:
            message = {
                "job_id": job_id,
                "rate" : howmuch,
                #"timestamp": timestamp
            }
        else:
            message = {
                "job_id": job_id,
                "rate" : howmuch,
                "timestamp": timestamp
            }

    records = []
    for i in range(nb_sources):
        record = {
            "value": message,
            "partition": i
        }
        records.append(record)

    payload = {
        "records" : records
    }
    headers = {'Content-type': 'application/vnd.kafka.json.v2+json'}
    r = requests.post(common.kafka_bridge_base_url + "/topics/nexmark-control", headers=headers, json=payload)

def reset_control_topic(name="test", partitions=5):
   delete_kafka_topic(name)
   sleep(10)
   create_kafka_topic(name, partitions)

def get_now():
    return int(datetime.now().timestamp() * 1000)

def change_rate_and_check(job_id, input_rate, size_window=30, slide_window=45, observation_size=20, nb_sources=5, cooldown_throughput=200, step="5s"):
    change_rate(job_id, cooldown_throughput, nb_sources=nb_sources)
    sleep(slide_window - size_window) # cooldown before next rate change

    change_rate(job_id, input_rate, nb_sources=nb_sources) 
    sleep(size_window)
    now = get_now()
    max_date = now
    min_date = now - observation_size * 1000
    df_detailed_run = prom_query_range(request_source_througput.format(job_id), min_date, max_date, step)
    logger.debug(df_detailed_run)
    return (df_detailed_run, min_date, max_date)

def loop_throughput_dichotomic_fn(job_id, initial_rate=10**8, size_window=30, slide_window=65, observation_size=30, timeout=300, mean_threshold=0.01, nb_sources=5, higher_bound_ratio=2, warmup=120, cooldown_throughput=200, limit_backpressure_source=250, monitoring_step="5s"):
    initial_time = get_now()
    rate = initial_rate 
    job_operators = get_job_operators_topological_order(job_id)
    operators_id = {job_operator["id"]:job_operator["description"] for job_operator in job_operators}
    df_detailed_run = None
    cpt = 0
    logger.debug("Setting to rate {}".format(rate))    
    (df_detailed_run, min_date, max_date) = change_rate_and_check(job_id, rate / nb_sources, warmup, warmup, warmup, nb_sources, cooldown_throughput, monitoring_step)
    mean = df_detailed_run["value"].mean()
    std = df_detailed_run["value"].std()    
    for id in operators_id:
        best_df_busy = prom_query_range(request_busy_avg.format(id, ".*", job_id), min_date, max_date, monitoring_step)
        logger.debug("Avg busy {}: {}".format(operators_id[id], best_df_busy["value"].mean()))
        if "Source" in operators_id[id]: 
            best_df_backpressured = prom_query_range(request_backpressured_avg.format(id, ".*", job_id), min_date, max_date, monitoring_step)
            logger.debug("Avg source backpressure {}: {}".format(operators_id[id], best_df_backpressured["value"].mean()))
            # workaround for low rate
            if best_df_backpressured["value"].mean() + best_df_busy["value"].mean() < limit_backpressure_source:
                return  (None, None, None, None, None)
    higher_bound = None
    lower_bound = 0
    rate = mean 
    best_df_detailed_run = None     
    best_rate = None
    best_df_sink = None
    best_df_busy = {}
    pbar = tqdm(total=timeout)
    pbar.set_description("Dichotomic")
    while True:
        cpt += 1
        logger.debug("Setting to rate {} (lower bound: {}, higher bound: {})".format(rate, lower_bound, higher_bound))
        (df_detailed_run, min_date, max_date) = change_rate_and_check(job_id, rate / nb_sources, size_window, slide_window, observation_size, nb_sources, cooldown_throughput, monitoring_step)
        mean = df_detailed_run["value"].mean()
        std = df_detailed_run["value"].std()
        logger.debug("Mean: {}, Std: {}".format(mean, std))
        for id in operators_id: 
            best_df_busy[id] = prom_query_range(request_busy_avg.format(id, ".*", job_id), min_date, max_date, monitoring_step)
            logger.debug("Avg busy {}: {}".format(operators_id[id], best_df_busy[id]["value"].mean()))

        if mean < (rate - (rate * mean_threshold)):
            logger.debug("Below threshold {} < {} (for an expected rate of {}) ".format(mean, (rate - (rate * mean_threshold)),rate))

            higher_bound = rate
        else:
            logger.debug("Above threshold {} > {} (for an expected rate of {}) ".format(mean, (rate - (rate * mean_threshold)), rate))
            lower_bound = rate
            best_df_detailed_run = df_detailed_run # we keep last good result
            best_rate = rate
            best_df_sink = prom_query_range(request_sink_throughput.format(job_id), min_date, max_date, monitoring_step)

        if higher_bound is None:
            logger.debug("Higher bound not set : multiply current rate by higher bound ratio {}".format(higher_bound_ratio))
            rate = higher_bound_ratio * rate
        else:
            rate = (higher_bound + lower_bound) / 2
        pbar.set_postfix(cpt=cpt, lower_bound=lower_bound, upper_bound=higher_bound)
        pbar.update((get_now() - initial_time)//1000 - pbar.n)
        if get_now() > initial_time + (timeout * 1000):
            logger.debug("Timeout dichotomic")
            return (best_rate, best_df_detailed_run, best_df_sink, cpt, best_df_busy)
        

def loop_estimation(list_xp, results_path="variable-results/estimation", topic="nexmark", details=[]):

    results_filename = "{}.csv".format(results_path)
    details_filename= "{}-details.yaml".format(results_path)
    run = 0

    objective = 0

    results = []

    pbar = tqdm(total=len(list_xp))
    for m in list_xp:
        if "limit_backpressure_source" in m:
            limit_backpressure_source = m ["limit_backpressure_source"]
        else: # no backpressure limit (previous behaviour)
            limit_backpressure_source = 1000

        if "monitoring_step" in m:
            monitoring_step = m["monitoring_step"]
        else:
            monitoring_step = "5s"
        nb_runs_throughput = m["nb_runs_throughput"]
        nb_runs_parallelism = m["nb_runs_parallelism"]

        params_datagen = { 
            "params": {
                "TPS": str(m["throughputs"][0]),
                "EVENTS_NUM": str(0),
                "PERSON_PROPORTION": str(1),
                "AUCTION_PROPORTION": str(3),
                "BID_PROPORTION": str(46),
                "NEXMARK_TABLE": "kafka", # datagen or kafka
                "TOPIC": "{};nexmark-control".format(topic),
                "BOOTSTRAP_SERVERS": "my-cluster-kafka-bootstrap.kafka:9092",
            },
            "notebook": m["notebook"],
            "timeout": 120,
        }

        task_parallelism = "" # default: nothing fixed, so 1
        (cpu, memory, run, task_slots_per_task_manager, source_parallelism, parallelism, evenly_spread, task_slots_limit) = (m["cpu"], m["memory"], m["run"], m["task_slots_per_task_manager"], m["source_parallelism"], m["parallelism"], m["evenly_spread"], m["task_slots_limit"])
        logger.debug ((cpu, memory, run, task_slots_per_task_manager, task_slots_limit))
        pbar.set_postfix(m)
        loop_throughput = True
        
        # read yaml
        if len(details) == 0:
            logger.debug("Reading details from {}".format(details_filename))
            try:
                with open(details_filename, 'r') as file:
                    details = yaml.unsafe_load(file)    
            except yaml.YAMLError as e:
                logger.error(f"The YAML file is not valid: {e}")
            except FileNotFoundError as e:
                logger.debug(f"File not found: {e}")
        # check existing previous task parallelism
        previous_memory_configurations = [val for val in details if (val["configuration"]["memory"] == memory) & (val["task_parallelism"] == "")]
        if len(previous_memory_configurations) > 0:
            logger.debug("Compute on archived 1-parallelism configuration")
            previous_memory_configuration = previous_memory_configurations[0]
            #task_parallelism = previous_memory_configurations[0]["task_parallelism"]
            (result, objective, parallelisms, rates) = solve_inverse_ds2(previous_memory_configuration["job_operators"], previous_memory_configuration["map_true_processing_rate"], previous_memory_configuration["map_cumulated_ratio"], task_slots_limit)
            logger.debug("Solver result: {} - {}".format(result, objective))
            #job_operators = get_job_operators_topological_order(previous_memory_configuration["job_id"])
            job_operators = previous_memory_configuration["job_operators"]
            task_parallelism = get_tasks_parallelism(job_operators, parallelisms)
            logger.debug(task_parallelism)

            adapt_parallelism = False
            run = nb_runs_parallelism
        else:
            adapt_parallelism = True            

        params_datagen_run = copy.deepcopy(params_datagen)

        params_query = { "params": {"SOURCES": str(source_parallelism), "PARALLELISM" : str(parallelism), "TASK_PARALLELISM": task_parallelism, "JOB_NAME": "{}-{}".format(results_path, "init")} }
        run_throughput = -1
        run = 0          
        pbar.set_description("Deploying test job")
        deploy("nexmark", flink_configuration(cpu=cpu,memory=memory,task_managers=m["task_managers_qty"], task_slots=task_slots_per_task_manager, evenly_spread=evenly_spread, custom_memory=m["custom_memory"]))
        sleep(10)
        if common.dynamic_flink_url:
            (_, base_url) = get_service_public_address("default", "jobmanager", "nexmark-flink-jobmanager", 8081)
            common.flink_base_url = base_url
        logger.debug("Flink: {}".format(common.flink_base_url))
        params_datagen_run["params"]["TPS"]=str(m["throughputs"][0]) # only the first is useful for now

        wait_for_task_managers(task_managers_qty=m["task_managers_qty"], base_url=common.flink_base_url)
        pbar.set_description("Parallelism convergence")
        pbar2 = tqdm()
        while loop_throughput:
            pbar2.set_description("Reset interpreter")
            status_code = reset_interpreter("flink")
            logger.debug ("Reset interpreter: {}".format(status_code))
            
            job_name = "{}-{}".format(results_path, run)
            params_query = { "params": {"SOURCES": str(source_parallelism), "PARALLELISM" : str(parallelism), "TASK_PARALLELISM": task_parallelism, "JOB_NAME": job_name} }

            job_ids = get_jobid_by_name(job_name) 
            if len(job_ids) > 0:
                job_id = get_jobid_by_name(job_name)[0]
                cancel_job(job_id)
            reset_control_topic("nexmark-control", source_parallelism)

            pbar2.set_description("Launch test notebook")
            launch_job_async(notebook=params_datagen_run["notebook"], params_query=params_query, params_datagen=params_datagen_run, timeout=300)
            sleep(30)
            job_id = get_jobid_by_name(job_name)[0]
            #df_detailed_run = loop_throughput_fn(job_id, initial_rate=int(params_datagen_run["params"]["TPS"]), size_window=30, slide_window=45, timeout=900)
            pbar2.set_description("MST determination")
            (_, df_detailed_run, df_sink_run, _, df_busy_detail) = loop_throughput_dichotomic_fn(job_id,
                initial_rate = m["dichotomic_mst_tuning"]["initial_rate"],
                size_window=m["dichotomic_mst_tuning"]["size_window"] ,
                slide_window=m["dichotomic_mst_tuning"]["slide_window"],
                observation_size=m["dichotomic_mst_tuning"]["observation_size"],
                timeout=m["dichotomic_mst_tuning"]["timeout"], 
                mean_threshold=m["dichotomic_mst_tuning"]["mean_threshold"], 
                higher_bound_ratio=m["dichotomic_mst_tuning"]["higher_bound_ratio"], 
                cooldown_throughput=m["dichotomic_mst_tuning"]["cooldown_throughput"], 
                nb_sources=source_parallelism, 
                warmup=m["warmup"],
                limit_backpressure_source=limit_backpressure_source,
                monitoring_step=monitoring_step)
            if df_detailed_run is None:
                logger.warn("Run has failed. Launching again.")
                continue
            logger.info("Obtained sink: {}".format(df_sink_run))
            if df_sink_run is None:
                logger.warn("No stable result obtained! Repeat test.")
                continue
            if df_sink_run["value"].mean() == 0:
                adapt_parallelism = True # for straggler we adapt parallelism if nothing comes out

            start_time = df_detailed_run["ts"].min() * 1000
            end_time = df_detailed_run["ts"].max() * 1000
            duration = end_time - start_time
            job_operators, map_true_processing_rate, map_cumulated_ratio = get_processing_stats(job_id, start_time, end_time)    

            map_operator_id = {j["id"]:j["description"] for j in job_operators}
            mean_busy = {d:df_busy_detail[d].max() for d in df_busy_detail if "Source" not in map_operator_id[d]}

            mean_observed_source_rate = df_detailed_run["value"].mean()
            median_observed_source_rate = df_detailed_run["value"].median()
            logger.info("Obtained throughput: mean:{} median:{}".format(mean_observed_source_rate, median_observed_source_rate))
            line_results = [params_datagen_run, task_parallelism, job_id, cpu, memory, m["task_managers_qty"], run_throughput, start_time, duration, task_slots_per_task_manager, source_parallelism, parallelism, evenly_spread, task_slots_limit, mean_observed_source_rate, objective] 
            results.append(line_results)

            with open(results_filename, 'a') as file:
                writer = csv.writer(file, delimiter=';')
                writer.writerow(line_results)
            file.close()
            detailed_results = {
                    "configuration": m,
                    "job_id": job_id,
                    "task_parallelism": task_parallelism,
                    "job_operators": job_operators,
                    "map_true_processing_rate": map_true_processing_rate,
                    "map_cumulated_ratio": map_cumulated_ratio,
                    "df_busy": df_busy_detail,
                }
            details.append(detailed_results)
            with open(details_filename, 'w') as file:
                yaml.dump(details, file)

            if adapt_parallelism:
                
                (result, objective, parallelisms, rates) = solve_inverse_ds2(job_operators, map_true_processing_rate, map_cumulated_ratio, task_slots_limit)
                logger.debug("Solver result: {} - {}".format(result, objective))
                job_operators = get_job_operators_topological_order(job_id)
                task_parallelism = get_tasks_parallelism(job_operators, parallelisms)
                logger.debug(task_parallelism)
                
                params_query = { "params": {"SOURCES": str(source_parallelism), "PARALLELISM" : str(parallelism), "TASK_PARALLELISM": task_parallelism} }
                # change throughput
                throughput = objective 
                #throughput = mean_observed_source_rate
                params_datagen_run["params"]["TPS"]=str(int(throughput))

                run += 1
                if run >= nb_runs_parallelism:
                    adapt_parallelism = False
                    run_throughput = 0
                    params_datagen_run["timeout"] = m["timeout"]
            else:
            #adapt_parallelism = True    
                run += 1
                run_throughput += 1
                if run_throughput >= nb_runs_throughput - 1:
                    loop_throughput = False
            pbar2.update(1)
        pbar.update(1)
    return(results_filename)

def loop_verification(list_xp, datagen_configuration, results_path="verification-results/results", detail_metrics=False):

    def get_job_name(name, throughput, run_ds2):
        return "{}-{}-{}".format(name, throughput, run_ds2)

    #sensibility_throughput = 0.05 # tentative : ratio expected vs real 
    results_filename = "{}.csv".format(results_path)
    # Deploy Flink datagen

    if datagen_configuration is not None:
        if "node_selector" not in datagen_configuration:
            datagen_configuration["node_selector"] = "jobmanager"
        datagen_flink_base_url = deploy_datagen(cpu=datagen_configuration["cpu"], memory=datagen_configuration["memory"], task_managers_qty=datagen_configuration["task_managers_qty"], task_slots=datagen_configuration["task_slots"], node_selector=datagen_configuration["node_selector"])

    pbar = tqdm(total=len(list_xp))
    for m in list_xp:
        pbar.set_description("Deploying test job")
        common.flink_base_url = deploy_sut(m)

        logger.debug("Testing configuration {}".format(m))

        delete_kafka_topic("nexmark-datagen")
        sleep(30)
        create_kafka_topic("nexmark-datagen", m["source_parallelism"])
        
        reset_interpreters()
        sleep(5)
        if datagen_configuration is not None:        
            params_datagen = { 
                "params": {
                    "NEXMARK_TABLE": "kafka", # datagen or kafka
                    "TOPIC": "nexmark-datagen",
                    "BOOTSTRAP_SERVERS": "my-cluster-kafka-bootstrap.kafka:9092",
                },
                "timeout": datagen_configuration["timeout"],
            }
        else:
            params_datagen = {
                "params": {
                    "NEXMARK_TABLE": "datagen", # datagen or kafka
                    "TOPIC": "nexmark-datagen",
                    "BOOTSTRAP_SERVERS": "my-cluster-kafka-bootstrap.kafka:9092",
                    "TPS": str(m["params.TPS"]),
                    "EVENTS_NUM": str(m["params.EVENTS_NUM"]),
                    "PERSON_PROPORTION": str(m["params.PERSON_PROPORTION"]),
                    "AUCTION_PROPORTION": str(m["params.AUCTION_PROPORTION"]),
                    "BID_PROPORTION": str(m["params.BID_PROPORTION"]),
                    
                },
                "timeout": m["timeout"],                
            }
        params_query = {
            "params": {
                "SOURCES": str(m["source_parallelism"]), 
                "PARALLELISM" : str(1), 
                "TASK_PARALLELISM": m["task_parallelism"],
                "JOB_NAME": get_job_name(results_path, 1000, -1),
            }
        }
        pbar.set_description("Launching workload with parallelism 1")
        logger.debug("Launching workload with parallelism 1 {} on SUT ".format(get_job_name(results_path, 1000, -1)))

        launch_job_async(notebook=m["notebook"], params_datagen=params_datagen, params_query=params_query, timeout=m["timeout"])
        sleep(30)
        # a custom parallelism has been set, we take the list of tasks of the actual job
        job_id = get_jobid_by_name(get_job_name(results_path, 1000, -1), base_url=common.flink_base_url)[0]
        job_operators = get_job_operators_topological_order(job_id)
        operators = [operator["description"] for operator in job_operators]
        #inject_kafka(get_job_name(name, throughput, run_ds2), 1000, 1000, base_url=datagen_flink_base_url, sink_qty=datagen_configuration["parallelism"])
        
        ## Get info from actual job (as tested are different because of time)
        job_operators = get_job_operators_topological_order(job_id)
        operators = [operator["description"] for operator in job_operators]

        parallelisms = m["task_parallelism"].split("|")
        actual_parallelisms = {}
        cpt = 0
        for operator in operators:
            if "Source" in operator in operator:
                continue
            actual_parallelisms[html.unescape(operator)] = int(parallelisms[cpt].split(";")[1])
            
            cpt += 1
        m["task_parallelism"] =  "|".join("{};{}".format(x.replace("$", "\$").replace("\"", "\\\\\\\""), actual_parallelisms[x]) for x in actual_parallelisms)
        params_query["params"]["TASK_PARALLELISM"] = m["task_parallelism"]
        cancel_job(job_id)

        run = 0
        logger.info ("Testing configuration {}".format(m))
        pbar2 = tqdm(total=len(m["throughputs"]))
        for throughput in m["throughputs"]:
            delete_kafka_topic("nexmark-datagen")
            sleep(30)
            create_kafka_topic("nexmark-datagen", m["source_parallelism"])            
            if datagen_configuration is not None: #
                params_datagen["params"]["TPS"] = str(int(throughput))
            else: 
                params_datagen["params"]["TPS"] = str(int(throughput / m["source_parallelism"]))

            params_query = {
                "params": {
                    "SOURCES": str(m["source_parallelism"]), 
                    "PARALLELISM" : str(1), 
                    "TASK_PARALLELISM": m["task_parallelism"],
                    "JOB_NAME": get_job_name(results_path, throughput, run),
                }
            }
            pbar2.set_description("Launching workload with custom parallelism")
            launch_job_async(notebook=m["notebook"], params_datagen=params_datagen, params_query=params_query, timeout=m["timeout"] + 30)
            sleep(30)
            job_id = get_jobid_by_name(get_job_name(results_path, throughput, run), base_url=common.flink_base_url)[0]
            if datagen_configuration is not None:
                pbar2.set_description("Launching datagen with throughput {}".format(throughput))
                logger.info("\nLaunch datagen {}".format(get_job_name(results_path, throughput, run)))
                datagen_job_id = inject_kafka(get_job_name(results_path, throughput, run), throughput, throughput*m["timeout"], base_url=datagen_flink_base_url, sink_qty=datagen_configuration["parallelism"], notebook=datagen_configuration["notebook"], timeout=m["timeout"])

                (start_time, duration, _) = get_job_info(datagen_job_id, base_url=common.datagen_flink_base_url)
            else:
                sleep(m["timeout"])
                (start_time, duration, _) = get_job_info(job_id, base_url=common.flink_base_url)
            real_throughput = get_throughput_source(job_id, start_time, start_time+duration, m["warmup"])["value"]

            cancel_job(job_id)
            if datagen_configuration is not None:
                cancel_job(datagen_job_id, base_url=common.datagen_flink_base_url)
            logger.info("Run {} - obtained throughput : {} (shift {} vs {} ) \n{}".format(
                run, 
                real_throughput.mean(), 
                ((throughput - real_throughput.mean()) / throughput),
                m["sensitivity"],
                m["task_parallelism"].replace("|", "\n")))
            
            results = []
            line_results = [m, m["task_parallelism"], job_id, m["cpu"], m["memory"], m["task_managers_qty"], throughput, start_time, duration, m["task_slots_per_task_manager"], m["source_parallelism"], m["parallelism"], m["evenly_spread"], m["task_slots_limit"], real_throughput.mean(), 0] 
            results.append(line_results)

            with open(results_filename, 'a') as file:
                writer = csv.writer(file, delimiter=';')
                writer.writerow(line_results)
            if detail_metrics:
                save_prom_to_hdf("{}-{}.h5".format(results_path, job_id), job_id, default_raw_queries)
                save_prom_to_hdf("{}-{}-details.h5".format(results_path, job_id), job_id, default_agg_queries)

            file.close()            
            run += 1
            pbar2.update(1)
            if ((throughput - real_throughput.mean()) / throughput)> m["sensitivity"]:
                logger.info("Sensitivity reached, pass to next configuration.")
                break
        pbar.update(1)
    return(results_filename)

def loop_ds2(list_xp, datagen_configuration, results_directory="ds2-results"):

    def get_job_name(name, throughput, run_ds2):
        return "{}-{}-{}".format(name, throughput, run_ds2)

    name = get_now()
    #sensibility_throughput = 0.05 # tentative : ratio expected vs real 
    max_ds2 = 3
    results_filename = "{}/results-{}.csv".format(results_directory, name)
    # Deploy Flink datagen
    common.datagen_flink_base_url = deploy_datagen(cpu=datagen_configuration["cpu"], memory=datagen_configuration["memory"], task_managers_qty=datagen_configuration["task_managers_qty"], task_slots=datagen_configuration["task_slots"])

    pbar = tqdm(total=len(list_xp))
    for m in list_xp:
        pbar.set_description("Deploying test job")
        common.flink_base_url = deploy_sut(m)
        logger.info ("Testing configuration {}".format(m))
        for throughput in m["throughputs"]:
            logger.debug("Testing throughput {}".format(throughput))
            run_ds2 = 0
            delete_kafka_topic("nexmark-datagen")
            create_kafka_topic("nexmark-datagen", m["source_parallelism"])
            
            #!curl -X PUT http://zeppelin.127-0-0-1.sslip.io:30081/api/interpreter/setting/restart/flink -H 'Content-Type: application/json' -d '{"noteId": "2HWKCZ7J6"}'
            reset_interpreters()
            sleep(5)

            params_datagen = { 
                "params": {
                    "NEXMARK_TABLE": "kafka", # datagen or kafka
                    "TOPIC": "nexmark-datagen",
                    "BOOTSTRAP_SERVERS": "my-cluster-kafka-bootstrap.kafka:9092",
                },
                "notebook": datagen_configuration["notebook"],
                "timeout": datagen_configuration["timeout"],
            }
            params_query = {
                "params": {
                    "SOURCES": str(m["source_parallelism"]), 
                    "PARALLELISM" : str(1), 
                    "TASK_PARALLELISM": m["task_parallelism"],
                    "JOB_NAME": get_job_name(name, throughput, run_ds2),
                }
            }
            pbar.set_description("Launching workload with parallelism 1")
            logger.debug("Launch workload {} on SUT ".format(get_job_name(name, throughput, run_ds2)))

            launch_job_async(notebook=params_datagen["notebook"], params_datagen=params_datagen, params_query=params_query, timeout=params_datagen["timeout"])
            sleep(30)

            logger.info("\nLaunch datagen {}".format(get_job_name(name, throughput, run_ds2)))
            datagen_job_id = inject_kafka(get_job_name(name, throughput, run_ds2), throughput, throughput*m["timeout"], base_url=datagen_flink_base_url, sink_qty=datagen_configuration["parallelism"], notebook=datagen_configuration["notebook"], timeout=m["timeout"])

            (start_time, duration, _) = get_job_info(datagen_job_id, base_url=common.datagen_flink_base_url)
            parallelisms = ds2(job_id, throughput, min_date=start_time, max_date=start_time + duration)
            job_operators = get_job_operators_topological_order(job_id)
            task_parallelism = get_tasks_parallelism(job_id, parallelisms)     
            real_throughput = get_throughput_source(job_id, start_time, start_time+duration)["value"].mean()
            cancel_job(job_id)
            logger.info("Run {} - obtained throughput : {} (shift {} vs {} ) \n{}".format(
                run_ds2, 
                real_throughput, 
                ((throughput - real_throughput) / throughput),
                m["sensitivity"],
                task_parallelism.replace("|", "\n")))
            ds2_running = ((throughput - real_throughput) / throughput) > m["sensitivity"]
            while ds2_running and run_ds2 < max_ds2:
                run_ds2 += 1

                # need to reset topic, as there could be still some messages from last run inside if slower
                delete_kafka_topic("nexmark-datagen")
                
                sleep(5)
                logger.debug("Launch init datagen (1000 messages)")
                #inject_kafka(get_job_name(name, throughput, run_ds2), 1000, 1000, base_url=datagen_flink_base_url, sink_qty=datagen_configuration["parallelism"])
                
                ## Get info from actual job (as tested are different because of time)
                job_operators = get_job_operators_topological_order(job_id)
                operators = [operator["description"] for operator in job_operators]

                parallelisms = m["task_parallelism"].split("|")
                actual_parallelisms = {}
                cpt = 0
                for operator in operators:
                    if "Source" in operator in operator:
                        continue
                    actual_parallelisms[operator] = int(parallelisms[cpt].split(";")[1])
                    
                    cpt += 1
                job_operators = get_job_operators_topological_order(job_id)
                m["task_parallelism"] = get_tasks_parallelism(job_operators, actual_parallelisms)

                params_query["params"]["TASK_PARALLELISM"] = task_parallelism
                params_query["params"]["JOB_NAME"] = get_job_name(name, throughput, run_ds2)
                logger.info("\nLaunch workload {} on SUT ".format(get_job_name(name, throughput, run_ds2)))

                pbar.set_description("Launching workload with DS2 parallelism (run {})".format(run_ds2))
                launch_job_async(notebook=params_datagen["notebook"], params_datagen=params_datagen, params_query=params_query, timeout=params_datagen["timeout"])
                sleep(30)

                job_id = get_jobid_by_name(get_job_name(name, throughput, run_ds2), base_url=common.flink_base_url)[0]
                logger.debug("\nLaunch datagen {}".format(get_job_name(name, throughput, run_ds2)))
                datagen_job_id = inject_kafka(get_job_name(name, throughput, run_ds2), throughput, throughput*m["timeout"], sink_qty=datagen_configuration["parallelism"], base_url=common.datagen_flink_base_url, notebook=datagen_configuration["notebook"])
                (start_time, duration, _) = get_job_info(datagen_job_id, base_url=common.datagen_flink_base_url)
                parallelisms = ds2(job_id, throughput, min_date=start_time + (m["warmup"] * 1000), max_date=start_time + duration, debug=True)            
                job_operators = get_job_operators_topological_order(job_id)
                task_parallelism = get_tasks_parallelism(job_operators, parallelisms)        
                
                real_throughput = get_throughput_source(job_id, start_time + (m["warmup"] * 1000), start_time+duration)["value"]
                
                cancel_job(job_id)
                results = []
                line_results = [m, ds2_running, throughput, start_time, duration, m["sensitivity"], max_ds2, real_throughput.mean(), real_throughput.std(), task_parallelism] 
                results.append(line_results)

                with open(results_filename, 'a') as file:
                    writer = csv.writer(file, delimiter=';')
                    writer.writerow(line_results)
                file.close()            
                logger.debug("Run {} - obtained throughput : {} (shift {} vs {} ) \n{}".format(
                    run_ds2, 
                    real_throughput.mean(), 
                    ((throughput - real_throughput.mean()) / throughput),
                    m["sensitivity"],
                    task_parallelism.replace("|", "\n")))
                ds2_running = ((throughput - real_throughput.mean()) / throughput) > m["sensitivity"]
            if run_ds2 == max_ds2:
                logger.warn("Did not reach {}, continue to next configuration".format(throughput))
                break
    return(results_filename)
