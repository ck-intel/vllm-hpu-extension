###############################################################################
# Copyright (C) 2024 Habana Labs, Ltd. an Intel Company
###############################################################################
import argparse
import json
import os
import sys

import numpy as np


def fix_cache_inputs(json_data, args):
    layer_indexes = set([int(key.split('.')[2]) for key in json_data['Nodes'].keys() if key.startswith('model.layers.')])
    for layer_index in range(len(layer_indexes)):
        matmul_av_input = None
        v_cache_input = None
        matmul_qk_input = None
        k_cache_input = None
        
        attn_name = "attn"
        k_cache_name = "k_cache"
        v_cache_name = "v_cache"
        if args.deepseek:
            attn_name = "mla_attn"
            k_cache_name = "latent_cache_k"

        matmul_av_key = f'model.layers.{layer_index}.self_attn.{attn_name}.impl.matmul_av'
        v_cache_key = f'model.layers.{layer_index}.self_attn.{attn_name}.impl.{v_cache_name}'
        matmul_qk_key = f'model.layers.{layer_index}.self_attn.{attn_name}.impl.matmul_qk'
        k_cache_key = f'model.layers.{layer_index}.self_attn.{attn_name}.impl.{k_cache_name}'
        
        matmul_av_input = json_data['Nodes'].get(matmul_av_key, {}).get('inputs', [None, None])[1]
        v_cache_input = json_data['Nodes'].get(v_cache_key, {}).get('inputs', [None])[0]
        matmul_qk_input = json_data['Nodes'].get(matmul_qk_key, {}).get('inputs', [None, None])[1]
        k_cache_input = json_data['Nodes'].get(k_cache_key, {}).get('inputs', [None])[0]

        if matmul_av_input != v_cache_input:
            if args.deepseek:
                # For deepseek, there is one tensor for k_cache and v_cache
                json_data['Nodes'][matmul_av_key]['inputs'][1] = k_cache_input
            else:
                json_data['Nodes'][matmul_av_key]['inputs'][1] = v_cache_input
        if matmul_qk_input != k_cache_input:
            json_data['Nodes'][matmul_qk_key]['inputs'][1] = k_cache_input

    return json_data


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Run the measurements parser", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-m", "--measurements", type=str, help="full path to the directory of the measurements that should be fixed"
    )
    parser.add_argument(
        "-o",
        "--out",
        type=str,
        default=os.getcwd(),
        help="path to the directory where the fixed measurements will be written",
    )
    parser.add_argument(
        "-d",
        "--deepseek",
        action="store_true",
        help="if handle deepseek models, please set this flag",
    )
    return parser.parse_args(args)


def main(args):
    args = parse_args(args)
    output_path = args.out
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    measurements_path = args.measurements
    measurements_paths = os.listdir(measurements_path)
    measurements_paths_ranges = [measurement_path for measurement_path in measurements_paths if measurement_path.endswith(
        ".json") and 'MAXABS_HW' not in measurement_path and "mod_list" not in measurement_path]
    measurements_paths_scales = [measurement_path for measurement_path in measurements_paths if measurement_path.endswith(
        ".json") and 'MAXABS_HW' in measurement_path and "mod_list" not in measurement_path]
    print(measurements_paths_ranges)
    print(measurements_paths_scales)
    for measurement in measurements_paths_ranges + measurements_paths_scales:
        fixed_json_path = os.path.join(
            output_path, f"{measurement.split(os.sep)[-1]}")
        with open(fixed_json_path, "w") as fixed_json_file:
            with open(os.path.join(measurements_path, measurement), "r") as json_file:
                data_to_fix = json.load(json_file)
                fixed_data = fix_cache_inputs(data_to_fix, args)
                json.dump(fixed_data, fixed_json_file)
                print("")
                print("measurement=", measurement, flush=True)
                print("measurements_paths_scales=",
                      measurements_paths_scales, flush=True)
                if measurement in measurements_paths_ranges + measurements_paths_scales:
                    global_rank = fixed_data["GlobalRank"]
                    local_rank = fixed_data["LocalRank"]
                    mode = fixed_data["Mode"]
                    nodes = fixed_data["Nodes"]
                    layers = {}
                    fixed_npz_path = fixed_json_path.replace(".json", ".npz")
                    for layer, dlayer in nodes.items():
                        layers[layer] = {}
                        layers[layer]["inputs"] = [
                            np.array(x) for x in dlayer["inputs"]]
                        if dlayer.get("outputs") is not None:
                            layers[layer]["outputs"] = [
                                np.array(x) for x in dlayer["outputs"]]
                        if dlayer.get("params") is not None and dlayer["params"].get("weight") is not None:
                            layers[layer]["params"] = {}
                            layers[layer]["params"]["weight"] = np.array(
                                dlayer["params"]["weight"])
                    df = {"GlobalRank": global_rank,
                          "LocalRank": local_rank, "Mode": mode, "Nodes": layers}
                    with open(fixed_npz_path, "w"):
                        np.savez(fixed_npz_path, df)

    print("finished fix_measurements script")


if __name__ == "__main__":
    main(sys.argv[1:])
