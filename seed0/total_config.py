exp_config = {
    'env': {
        'manager': {
            'episode_num': float("inf"),
            'max_retry': 5,
            'step_timeout': 60,
            'auto_reset': True,
            'reset_timeout': 60,
            'retry_waiting_time': 0.1,
            'shared_memory': True,
            'context': 'fork',
            'wait_num': float("inf"),
            'step_wait_timeout': None,
            'connect_timeout': 60,
            'force_reproducibility': False,
            'cfg_type': 'SyncSubprocessEnvManagerDict',
            'type': 'subprocess'
        },
        'type': 'smac_ace',
        'import_names': ['dizoo.smac.envs.smac_env_ace'],
        'map_name': '5m_vs_6m',
        'difficulty': 7,
        'reward_type': 'original',
        'agent_num': 5,
        'collector_env_num': 8,
        'evaluator_env_num': 8,
        'stop_value': 1.999,
        'n_evaluator_episode': 32
    },
    'policy': {
        'model': {
            'agent_num': 5,
            'embed_num': 6,
            'state_len': 33,
            'relation_len': 6,
            'hidden_len': 256,
            'local_pred_len': 6,
            'global_pred_len': 12
        },
        'learn': {
            'learner': {
                'train_iterations': 1000000000,
                'dataloader': {
                    'num_workers': 0
                },
                'hook': {
                    'load_ckpt_before_run': '',
                    'log_show_after_iter': 2000,
                    'save_ckpt_after_iter': 10000000000,
                    'save_ckpt_after_run': True
                },
                'cfg_type': 'BaseLearnerDict'
            },
            'multi_gpu': False,
            'update_per_collect': 50,
            'batch_size': 160,
            'learning_rate': 0.0003,
            'clip_value': 50,
            'target_update_theta': 0.008,
            'discount_factor': 0.99,
            'nstep': 3,
            'shuffle': True,
            'aux_loss_weight': {
                'begin': 10,
                'end': 10,
                'T_max': 400000
            },
            'learning_rate_type': 'cosine',
            'weight_decay': 1e-05,
            'optimizer_type': 'rmsprop',
            'double_q': False,
            'aux_label_norm': True,
            'learning_rate_tmax': 60000,
            'learning_rate_eta_min': 3e-06
        },
        'collect': {
            'collector': {
                'deepcopy_obs': False,
                'transform_obs': False,
                'collect_print_freq': 100,
                'get_train_sample': True,
                'cfg_type': 'EpisodeSerialCollectorDict',
                'type': 'episode'
            },
            'unroll_len': 1,
            'n_episode': 32,
            'env_num': 8
        },
        'eval': {
            'evaluator': {
                'eval_freq': 1000,
                'cfg_type': 'InteractionSerialEvaluatorDict',
                'stop_value': 1.999,
                'n_episode': 32
            },
            'env_num': 8
        },
        'other': {
            'replay_buffer': {
                'type': 'advanced',
                'replay_buffer_size': 300000,
                'max_use': float("inf"),
                'max_staleness': 1000000000.0,
                'alpha': 0.6,
                'beta': 0.4,
                'anneal_step': 100000,
                'enable_track_used_data': False,
                'deepcopy': False,
                'thruput_controller': {
                    'push_sample_rate_limit': {
                        'max': float("inf"),
                        'min': 0
                    },
                    'window_seconds': 30,
                    'sample_min_limit_ratio': 1
                },
                'monitor': {
                    'sampled_data_attr': {
                        'average_range': 5,
                        'print_freq': 200
                    },
                    'periodic_thruput': {
                        'seconds': 60
                    }
                },
                'cfg_type': 'AdvancedReplayBufferDict',
                'max_reuse': 1000000000.0
            },
            'eps': {
                'type': 'linear',
                'start': 1,
                'end': 0.05,
                'decay': 50000
            },
            'commander': {
                'cfg_type': 'BaseSerialCommanderDict'
            }
        },
        'type': 'smac_ace_dqn_command',
        'cuda': True,
        'on_policy': False,
        'priority': False,
        'priority_IS_weight': False,
        'cfg_type': 'SMACACEDQNCommandModePolicyDict'
    },
    'exp_name': 'seed0',
    'seed': 0
}