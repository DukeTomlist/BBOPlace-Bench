problem_formulation=sp
algo=ea
benchmark_prefix=superblue

for i in 1 3 4 5 7 10 16 18
do
benchmark=${benchmark_prefix}${i}
python ../src/main.py \
    --name=ICCAD2015_SP_EA_MP \
    --benchmark=${benchmark} \
    --placer=${problem_formulation} \
    --algorithm=${algo} \
    --run_mode=single \
    --n_cpu_max=10 \
    --eval_gp_hpwl=False \
    --n_population=50 \
    --n_sampling_repeat=5 \
    --max_evals=10000 \
    --max_eval_time=72 \
    --n_macro=512 \
    --sampling=random \
    --mutation=inversion \
    --crossover=order
done