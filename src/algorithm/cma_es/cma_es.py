import cma 
import ray
import pickle 
import numpy as np 
import logging
from utils.debug import * 
from utils.constant import INF 
from utils.random_parser import set_state
from placer.dmp_placer import params_space
from ..basic_algo import BasicAlgo
from algorithm.ea.pymoo_problem import (
    GridGuidePlacementProblem,
    SequencePairPlacementProblem,
    HyperparameterPlacementProblem
)
import time 
import os 

from algorithm.ea.operators import REGISTRY as OPS_REGISTRY

@ray.remote(num_cpus=1, num_gpus=1)
def evaluate_placer(placer, x0):
    return placer.evaluate(x0)

class CMAES(BasicAlgo):
    def __init__(self, args, placer, logger):
        super(CMAES, self).__init__(args=args, placer=placer, logger=logger)
        self.node_cnt = placer.placedb.node_cnt
        self.best_hpwl = INF 
        
        if args.placer == "grid_guide":
            self.problem = GridGuidePlacementProblem(
                n_grid_x=args.n_grid_x,
                n_grid_y=args.n_grid_y,
                placer=placer
            )
            self.xl = np.zeros(self.node_cnt * 2)
            self.xu = np.array(
                ([args.n_grid_x] * self.node_cnt) + \
                    ([args.n_grid_y] * self.node_cnt)
            )
        elif args.placer == "sp":
            self.xl = np.zeros(self.node_cnt * 2)
            self.xu = np.array([self.node_cnt] * self.node_cnt * 2)
            self.problem = SequencePairPlacementProblem(
                placer=placer
            )
        elif args.placer == "dmp":
            extract = lambda ent_i: \
                [entry[ent_i] for entry in params_space.values()]
            self.xl = np.array(extract(0))
            self.xu = np.array(extract(1))
            self.problem = HyperparameterPlacementProblem(
                params_space=params_space,
                placer=placer,
            )
        else:
            raise NotImplementedError
        
        self.args.__dict__.update(
            {"logger": logger, "record_func": self._record_results}
        )  
    
    def run(self):
        self.t = time.time() 
        
        checkpoint = self._load_checkpoint()
        if checkpoint is not None:
            self.cmaes = checkpoint["obj"]
        else:
            x_init = OPS_REGISTRY["sampling"][self.args.placer]["random"](self.args, self.placer) \
                    .do(self.problem, 1).get("X")
            self.cmaes = cma.CMAEvolutionStrategy(
                x_init, 
                self.args.sigma,
                {
                    "popsize": self.args.pop_size,
                    "bounds": [self.xl, self.xu],
                    "seed": self.args.seed
                }
            )
        
        def round_to_discrete(x):
            return np.round(x).astype(int)
        
        while self.n_eval < self.args.max_evals:
            population = self.cmaes.ask()
            fitness = [] 
            overlap_rate = []
            macro_pos_all = []
            
            if self.args.placer == "grid_guide":
                processed_population = [round_to_discrete(x) for x in population]
            elif self.args.placer == "sp":
                raise ValueError("CMA-ES is not supported for SP")
            elif self.args.placer == "dmp":
                processed_population = population
            
            if ray.available_resources().get("CPU", 0) > 1:
                futures = [evaluate_placer.remote(self.placer, x0) for x0 in processed_population]
                results = ray.get(futures)
            else:
                results = [self.placer.evaluate(x0) for x0 in processed_population]
            
            for hpwl, o_r, macro_pos in results:
                fitness.append(hpwl)
                overlap_rate.append(o_r)
                macro_pos_all.append(macro_pos)
                
            t_temp = time.time() 
            t_eval = t_temp - self.t 
            self.t_total += t_eval
            t_each_eval = t_eval / self.args.pop_size 
            avg_t_each_eval = self.t_total / (self.n_eval + self.args.pop_size)
            self.t = t_temp
            
            self._record_results(np.array(fitness), np.array(overlap_rate), macro_pos_all,
                                t_each_eval=t_each_eval,
                                avg_t_each_eval=avg_t_each_eval)
            
            self._save_checkpoint() 
                
            

    def _load_checkpoint(self):
        if hasattr(self.args, "checkpoint") and os.path.exists(self.args.checkpoint):
            super()._load_checkpoint()
            with open(os.path.join(self.args.checkpoint, "cma_es.pkl"), "rb") as f:
                checkpoint = pickle.load(f)
                self.start_from_checkpoint = True
        else:
                checkpoint = None
                self.start_from_checkpoint = False
        
        return checkpoint
    

    
    def _save_checkpoint(self):
        super()._save_checkpoint()

        with open(os.path.join(self.checkpoint_path, "cma_es.pkl"), "wb") as f:
            pickle.dump(
                {
                    "obj" : self.cmaes,
                },
                file=f
            )
        
