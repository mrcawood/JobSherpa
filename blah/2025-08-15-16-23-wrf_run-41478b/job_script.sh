#!/bin/bash





#SBATCH --job-name=wrf-run
#SBATCH --output=slurm/slurm-%j.out
#SBATCH --error=slurm/slurm-%j.err
#SBATCH --partition=
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=56
#SBATCH --time=02:00:00



cd blah/2025-08-15-16-23-wrf_run-41478b

srun wrf.exe

