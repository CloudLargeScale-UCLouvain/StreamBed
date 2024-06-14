import pulp
import datetime
import html
import math
from graphlib import TopologicalSorter
import logging
from common_flink import *
from collections import OrderedDict

logger = logging.getLogger('streambed')

def get_operator_by_id(id, job_operators):
    for j in job_operators:
        if j["id"] == id:
            return j

    return None

def get_processing_stats(job_id, min_date=None, max_date=None, step="5s"):
    (start_time, duration, source_write_records_qty) = get_job_info(job_id = job_id)
    if min_date is None:
        min_date = start_time   
    if max_date is None:
        max_date = start_time + duration
    logger.info("Solving inverse DS2 on {} (start: {}, duration: {})".format(job_id, min_date,max_date-min_date))
    job_operators = get_job_operators_topological_order(job_id)

    map_true_processing_rate = {}
    map_true_output_rate = {}
    map_ratio_input_output = {}
    map_cumulated_ratio = {}
    map_ratio_source = {}
    rate_source = 0
    source_qty = 0

    ### compute real rates & ratios
    for operator in job_operators:
        
        logger.debug("{} //{}".format(operator["description"], operator["parallelism"]))

        df_detailed_run = prom_query_range(request_input_throughput.format(operator["id"],job_id), min_date, max_date, step)
        observed_processing_rate = df_detailed_run["value"].mean()
        df_detailed_run = prom_query_range(request_output_throughput.format(operator["id"],job_id), min_date, max_date, step)
        observed_output_rate = df_detailed_run["value"].mean()

        df_detailed_run = prom_query_range(request_busy.format(operator["id"],".*", job_id), min_date, max_date, step)
        busyness = df_detailed_run["value"].mean()
        if observed_processing_rate != 0:
            ratio_input_output = observed_output_rate / observed_processing_rate
        else:
            ratio_input_output = 1.
        logger.debug("  Obs.: {} |({})> {} - // {}, Ratio: {}".format(observed_processing_rate, busyness, observed_output_rate, operator["parallelism"], ratio_input_output))    
        if busyness == 0:
            logger.warn("Busyness zero for {}/{}, set to 1.".format(operator["id"], operator["description"]))
            busyness = 1
        true_processing_rate = (observed_processing_rate / (busyness / 1000)) 
        true_output_rate = (observed_output_rate / (busyness / 1000)) 

        map_true_processing_rate[operator["id"]] = true_processing_rate
        map_true_output_rate[operator["id"]] = true_output_rate
        map_ratio_input_output[operator["id"]] = ratio_input_output
        #print("Potential output rate " + bcolors.OKGREEN + "{}".format(true_output_rate) + bcolors.ENDC)
        logger.debug("  True: {} |({})> {} - ".format(true_processing_rate, 1000, true_output_rate))    

        if "Source" in operator["description"]:
            rate_source += observed_output_rate
            source_qty += operator["parallelism"]
            
        logger.debug("Rate source {}".format(rate_source))
        map_cumulated_ratio[operator["id"]] = []
        if "inputs" in operator:
            for previous_operator in operator["inputs"]:
                map_cumulated_ratio[operator["id"]].append(ratio_input_output * map_cumulated_ratio[previous_operator["id"]])
            map_cumulated_ratio[operator["id"]] = sum(map_cumulated_ratio[operator["id"]])            
            map_ratio_source[operator["id"]] = observed_output_rate / rate_source
            logger.debug("Cumulated: {} - Ratio vs source {}".format(map_cumulated_ratio[operator["id"]],  map_ratio_source[operator["id"]]))
        else: 
            map_cumulated_ratio[operator["id"]].append(1.)
            map_cumulated_ratio[operator["id"]] = sum(map_cumulated_ratio[operator["id"]])            
        logger.debug("------------------------------------------------------")
    return job_operators, map_true_processing_rate, map_cumulated_ratio

def solve_inverse_ds2(job_operators, map_true_processing_rate, map_cumulated_ratio, task_slots_qty, source_qty=None):

    if source_qty is None:
        source_qty = sum(m["parallelism"] for m in job_operators if "Source" in m["description"])

    ### model generation
    max_bound = task_slots_qty - source_qty

    operators = [j["id"] for j in job_operators if "Source" not in j["description"]]
    initial_rate = pulp.LpVariable("initial_rate", lowBound=0, cat=pulp.LpContinuous)
    parallelism = pulp.LpVariable.dicts("parallelism", operators, lowBound=1, upBound=max_bound, cat=pulp.LpInteger)
    rate = pulp.LpVariable.dicts("rate", operators, lowBound=0, cat=pulp.LpContinuous)

    inverse_ds2 = pulp.LpProblem("inverse_borned_DS2", pulp.LpMaximize)
    inverse_ds2 += pulp.lpSum(initial_rate) # objective function
    for operator in operators:
        ### constraints for each operator
        op = get_operator_by_id(operator, job_operators)
        logger.debug("Solver: add operator {}".format(op["description"]))
        if "Source" in op["description"]:
            continue

        inverse_ds2 += (rate[operator] == parallelism[operator] * map_true_processing_rate[operator], f"capacity_{operator}")

        array_inputs = []
        if "inputs" in op:
            for previous_operator in op["inputs"]:
                array_inputs.append(initial_rate * map_cumulated_ratio[previous_operator["id"]])
            logger.debug(array_inputs)
            inverse_ds2 += (pulp.lpSum(array_inputs) <= rate[operator], f"sum_previous_{operator}")

    inverse_ds2 += (pulp.lpSum(parallelism[operator] for operator in operators) == max_bound, "task_slot_capacity")

    ### solve
    result = inverse_ds2.solve(solver=pulp.PULP_CBC_CMD(msg=0))
    logger.debug("Solver result: {}".format(pulp.LpStatus[result]))
    
    ### generate results
    map_parallelism = {}
    map_rate = {}
    for v in inverse_ds2.variables():
        logger.debug("{} : {}".format(v.name, v.varValue))

        splitted_name = v.name.split("_")
        if splitted_name[0] == "parallelism":
            map_parallelism[splitted_name[1]] = v.varValue
        if splitted_name[0] == "rate":
            map_rate[splitted_name[1]] = v.varValue
       
    return (result, inverse_ds2.objective.value(), map_parallelism, map_rate)

# original getting parallelism from running job
def get_task_parallelism(job_id, parallelisms, debug=False):
    task_parallelism = OrderedDict()
    job_operators = get_job_operators_topological_order(job_id)
    for operator in job_operators:
        for parallelism in parallelisms:
            if parallelism == operator["id"]:
                task_parallelism[html.unescape(operator["description"])] = int(parallelisms[parallelism])
    logger.debug(task_parallelism)
    
    return "|".join("{};{}".format(x.replace("$", "\$").replace("\"", "\\\\\\\""), task_parallelism[x]) for x in task_parallelism)

def get_tasks_parallelism(job_operators, parallelisms):
    task_parallelism = OrderedDict()
    for operator in job_operators:
        for parallelism in parallelisms:
            if parallelism == operator["id"]:
                task_parallelism[html.unescape(operator["description"])] = int(parallelisms[parallelism])
    logger.debug(task_parallelism)
    
    return "|".join("{};{}".format(x.replace("$", "\$").replace("\"", "\\\\\\\""), task_parallelism[x]) for x in task_parallelism)


def ds2(job_id, rate, debug=False, min_date=None, max_date=None, rampup=30, step="5s"):
    (start_time, duration, source_write_records_qty) = get_job_info(job_id = job_id)
    job_operators = get_job_operators_topological_order(job_id)    


    map_true_processing_rate = {}
    map_true_output_rate = {}
    map_ratio_input_output = {}
    map_cumulated_ratio = {}
    map_ratio_source = {}
    rate_source = 0
    source_qty = 0
    sink_qty = 0

    ### compute real rates & ratios
    for operator in job_operators:
        logger.debug("{} //{}".format(operator["description"], operator["parallelism"]))
        
        if min_date is None:
            min_date = start_time   
        if max_date is None:
            max_date = start_time + duration
        df_detailed_run = prom_query_range(request_input_throughput.format(operator["id"],job_id), min_date, max_date, step)
        observed_processing_rate = df_detailed_run[df_detailed_run.second > rampup]["value"].mean()
        df_detailed_run = prom_query_range(request_output_throughput.format(operator["id"],job_id), min_date, max_date, step)
        observed_output_rate = df_detailed_run[df_detailed_run.second > rampup]["value"].mean()
        #display("{} {} {}".format(request_busy.format(operator["id"],".*", job_id), min_date, max_date))
        df_detailed_run = prom_query_range(request_busy.format(operator["id"],".*", job_id), min_date, max_date, step)
        #display(df_detailed_run)
        busyness = df_detailed_run[df_detailed_run.second > rampup]["value"].mean()
        if observed_processing_rate != 0:
            ratio_input_output = observed_output_rate / observed_processing_rate
        else:
            ratio_input_output = 1.
        logger.debug("  Obs.: {} |({})> {} - Ratio: {}".format(observed_processing_rate, busyness, observed_output_rate, ratio_input_output))    
        true_processing_rate = observed_processing_rate / (busyness / 1000) 
        true_output_rate = observed_output_rate / (busyness / 1000) 
        map_true_processing_rate[operator["id"]] = true_processing_rate
        map_true_output_rate[operator["id"]] = true_output_rate
        map_ratio_input_output[operator["id"]] = ratio_input_output

        #print("Potential output rate " + bcolors.OKGREEN + "{}".format(true_output_rate) + bcolors.ENDC)
        logger.debug("  True: {} |({})> {} - ".format(true_processing_rate, 1000, true_output_rate), end="")    

        if "Source" in operator["description"]:
            rate_source += observed_output_rate
            source_qty += operator["parallelism"]
        if "Sink" in operator["description"]:
            sink_qty += 1
            
        logger.debug("Rate source {}".format(rate_source))
        map_cumulated_ratio[operator["id"]] = []
        if "inputs" in operator:
            for previous_operator in operator["inputs"]:
                map_cumulated_ratio[operator["id"]].append(ratio_input_output * map_cumulated_ratio[previous_operator["id"]])
            map_cumulated_ratio[operator["id"]] = sum(map_cumulated_ratio[operator["id"]])            
            #map_ratio_source[operator["id"]] = observed_output_rate / rate_source
            map_ratio_source[operator["id"]] = observed_processing_rate / rate_source
            logger.debug("Cumulated: {} - Ratio vs source {}".format(map_cumulated_ratio[operator["id"]],  map_ratio_source[operator["id"]]))
        else: 
            map_cumulated_ratio[operator["id"]].append(1.)
            map_cumulated_ratio[operator["id"]] = sum(map_cumulated_ratio[operator["id"]])            
        logger.debug("------------------------------------------------------")
    logger.debug("Desired rate: {}".format(rate))
    
    operators = [j for j in job_operators if "Source" not in j["description"] and "Sink" not in j["description"]]
    map_parallelism = {}
    for operator in operators:
        array_inputs = []
        for previous_operator in operator["inputs"]:        
            array_inputs.append(map_cumulated_ratio[previous_operator["id"]])
        if map_true_processing_rate[operator["id"]] > 0:
            target_parallelism = (rate * map_ratio_source[operator["id"]]) / map_true_processing_rate[operator["id"]]
        else:
            target_parallelism = 1
        logger.debug(operator["description"])
        logger.debug("{} x {} = {} / {} = {} (=> {}) ".format(
            rate,
            map_ratio_source[operator["id"]],
            rate * map_ratio_source[operator["id"]],
            map_true_processing_rate[operator["id"]],
            target_parallelism,
            math.ceil(target_parallelism)
        ))
        map_parallelism[operator["id"]] = math.ceil(target_parallelism)

    return map_parallelism

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def convert_timestamp_to_timezone(timestamp_ms, target_timezone = "Europe/Paris"):
    # Convert milliseconds to a datetime object in UTC+2
    datetime_utcplus2 = datetime.utcfromtimestamp(timestamp_ms / 1000)

    # Define the UTC+2 offset in hours
    utcplus2_offset = timedelta(hours=2)

    # Apply the UTC+2 offset to the datetime object
    datetime_utc = datetime_utcplus2 + utcplus2_offset

    # Convert the datetime object to a UTC timestamp in milliseconds
    timestamp_utc = datetime_utc.timestamp() * 1000
    return timestamp_utc

import pandas as pd
from prometheus_pandas import query

def save_prom_to_hdf(filename, job_id, queries):
    (start_time, duration, _) = get_job_info(job_id)
    store = pd.HDFStore(filename)
    import tqdm
    p = query.Prometheus(common.prometheus_base_url)
    start = convert_timestamp_to_timezone(start_time)/1000
    end = convert_timestamp_to_timezone(start_time+duration)/1000
    logger.debug("Saving Prometheus metrics from {} ({}->{}) to {} ({})".format(job_id, start, end, filename, queries.keys()))
    for q in tqdm.tqdm(queries):
        d = {"job_id":job_id}        
        df = p.query_range(queries[q].format(**d), 
                        start, 
                        end, "5s")        
        store.put(q, df)
    store.close()