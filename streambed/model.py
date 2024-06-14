import math
import yaml
import json
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import PolynomialFeatures, FunctionTransformer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import LeaveOneOut, cross_val_score
from sklearn.pipeline import make_pipeline

from common_alloc import *
from common import *

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging
from sklearn.base import clone

class InfrastructureRegression:
    
    def __init__(self):
        self.raw_data = None
        self.data = None
        self.data_details = []
        self.models = {}    
    def load(self, path):
        df = pd.read_csv(path, sep=";", header=None, names=["params_datagen_run", "task_parallelism", "job_id", "cpu", "memory", "task_managers_qty", "run", "start_time", "duration", "task_slots", "source_parallelism", "parallelism", "evenly_spread", "task_slots_limit", "observed_source_rate", "objective"])
        raw_data = df
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
        test = test.add_prefix("query.")

        df =pd.concat([df, test.astype(int)], axis=1)
        df["params.TPS"] = df["params.TPS"].astype(int)
        df["used_task_slots"] = df.filter(regex="query\..*").sum(axis=1)
        if self.data is None:
            self.data = df
            self.raw_data = raw_data
        else:
            self.data = pd.concat([self.data, df])
            self.raw_data = pd.concat([self.raw_data, raw_data])

    def load_full(self, paths, reset = True):
        if reset:
            self.data = None
            self.raw_data = None
            self.data_details = []
        for path in paths:
            raw_data = pd.read_csv(path + ".csv", sep=";", header=None, names=["params_datagen_run", "task_parallelism", "job_id", "cpu", "memory", "task_managers_qty", "run", "start_time", "duration", "task_slots", "source_parallelism", "parallelism", "evenly_spread", "task_slots_limit", "observed_source_rate", "objective"])

            (df, _) = read_results(path + ".csv")
            if self.data is None:
                self.data = df
                self.raw_data = raw_data
            else:
                self.data = pd.concat([self.data, df])
                self.raw_data = pd.concat([self.raw_data, raw_data])
            self.load_details(path + "-details.yaml")

    def save(self, path):
        self.raw_data.to_csv(path + ".csv", header=None, index=False, sep=";")
        with open(path + "-details.yaml", 'w') as file:
            yaml.dump(self.data_details, file)        
        

    def filter_data(self, query="", drop_duplicates=False, drop_na=False):
        if query != "":
            self.data = self.data.query(query)
        if drop_na:
            self.data = self.data.dropna()
        if drop_duplicates:
            self.data = self.data.sort_values(["start_time"], ascending=False).drop_duplicates(subset=["memory", "used_task_slots"])
        jobs_id = self.data["job_id"].to_list()
        filtered_details = []
        for detail in self.data_details:
            if detail["job_id"] in jobs_id:
                filtered_details.append(detail)
        self.data_details = filtered_details
        self.raw_data = self.raw_data[(self.raw_data["job_id"].isin(jobs_id))]

    def clear(self):
        self.data = None

    def generic_model(self, name, pipeline, data=None):
        if data is None:
            data = self.data[["used_task_slots", "memory", "observed_source_rate"]]        
        X = data.iloc[:, :-1].values
        y = data.iloc[:, -1].values

        # Create the Leave-One-Out cross-validator
        loo = LeaveOneOut()
        model = pipeline
        scores = cross_val_score(model, X, y, cv=loo, scoring='neg_root_mean_squared_error')
        mean_score = np.mean(scores)
        model.fit(X ,y)
        self.models[name] = model
        return (model, mean_score)

    def set_model(self, name, model):
        self.models[name] = model

    def generic_models(self, pipeline, min_samples, size):
        models = []
        mean_scores = []
        data = self.data[["used_task_slots", "memory", "observed_source_rate"]]        
        for i in range(min_samples,size):
            X = data.iloc[:i+1, :-1].values
            y = data.iloc[:i+1, -1].values

            # Create the Leave-One-Out cross-validator
            loo = LeaveOneOut()
            model = clone(pipeline)
            scores = cross_val_score(model, X, y, cv=loo, scoring='neg_root_mean_squared_error')
            mean_score = np.mean(scores)
            model.fit(X ,y)
            models.append(model)
            mean_scores.append(mean_score)
            #self.models[name] = model
        return (models, mean_scores)

    def objective_function_loo(models, X, y):
        loo = LeaveOneOut()
        
        min_mse = float('inf')
        mse_by_model = {}
        if len(X) > 1:
            for model_name in models:
                model = clone(models[model_name])
                scores = cross_val_score(model, X, y, cv=loo, scoring='neg_root_mean_squared_error')
                
                # Compute the average MSE (scores are negative, so we negate the result)
                mse_avg = -1 * scores.mean()
                mse_by_model[model_name] = mse_avg

                if mse_avg < min_mse:
                    min_mse = mse_avg
        else:
            return 0, {}
        return min_mse, mse_by_model

    def predict(self, name, used_task_slots, memory):
        data = self.data[["used_task_slots", "memory", "observed_source_rate"]]
        X = data.iloc[:, :-1].values
        y = data.iloc[:, -1].values

        
        y_predict = self.models[name].predict(X)
        input_array = np.column_stack((np.array(used_task_slots), np.array(memory)))
        throughput = self.models[name].predict(input_array)

        return throughput
    
    def load_details(self, path):
        with open(path, "r") as stream:
            details = yaml.unsafe_load(stream)
            self.data_details.extend(details)
            
    def find_details(self, ts, memory):
        found = [d for d in self.data_details if 
                    d["configuration"]["memory"] == memory and
                    d["configuration"]["task_slots_limit"] == ts 
                ]
        return(found)    

    def compute_x(self, model_name, target_throughput, cpu_bounds, memory_bounds):
        target_y = target_throughput
        candidates = []
        for x2 in memory_bounds:
            for x1 in cpu_bounds:
                x = np.array([x1, x2]).reshape(1,-1)
                y_pred = self.predict(model_name, x1, x2)
                if y_pred >= target_y:
                    candidates.append([x1, x2]) 
                    break
        return candidates

    def get_parallelism(self, cpu, memory, needed_sources, source_capacity=400000):
        task_slots_limit = max([d["configuration"]["task_slots_limit"] for d in self.data_details if d["configuration"]["memory"] == memory])

        run = [d for d in self.data_details if 
                            d["configuration"]["memory"] == memory and
                            d["configuration"]["task_slots_limit"] == task_slots_limit
                        ][0]
        job_operators = run["job_operators"]
        (result, objective, parallelisms, rates) = solve_inverse_ds2(job_operators, run["map_true_processing_rate"], run["map_cumulated_ratio"], cpu+needed_sources, needed_sources)
        task_parallelism = get_tasks_parallelism(job_operators, parallelisms)
        
        return task_parallelism

    def get_parallelism_throughput(self, throughput, memory, source_capacity=400_000, model_name="linear"):
        needed_sources = math.ceil(throughput / source_capacity)

        candidates = self.compute_x(model_name, throughput, range(3,1600), [memory])
        print(candidates)
        return self.get_parallelism(candidates[0][0], candidates[0][1], needed_sources), candidates[0][0], needed_sources

    def generate_config_throughput(self, config, model_type):
        task_parallelism, task_slots, needed_sources = self.get_parallelism_throughput(config["throughputs"][0], config["memory"], config["source_capacity"], model_name=model_type)        
        tm_qty = math.ceil((task_slots + needed_sources)/ config["task_slots_per_task_manager"])
        actual_needed_task_managers_qty = math.ceil(tm_qty / config["ratio_tm"])        
        config["task_parallelism"] = task_parallelism
        config["task_managers_qty"] = actual_needed_task_managers_qty
        config["source_parallelism"] = needed_sources
        return config
    
    def heatmap(self):
        pivot_table = self.data.pivot_table(index='used_task_slots', columns='memory', values='observed_source_rate', aggfunc=np.mean)

        # Plot the heatmap using Seaborn's heatmap() function
        sns.heatmap(pivot_table, cmap='coolwarm', annot=True, fmt='.2f')
        plt.xlabel('memory')
        plt.ylabel('cores')
        plt.title('Heatmap of Actual Y values (X1 on Y-axis, X2 on X-axis)')
        plt.show()
