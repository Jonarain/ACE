import copy
from collections import namedtuple
from typing import List, Dict, Any, Tuple, Union

import numpy as np
import torch
import torch.nn.functional as F

from ding.model import model_wrap
from ding.rl_utils import q_v_1step_td_error, q_v_1step_td_data, get_train_sample
from ding.torch_utils import Adam, to_device
from ding.utils import POLICY_REGISTRY
from ding.utils.data import default_collate, default_decollate
from .base_policy import Policy
from .common_utils import default_preprocess_learn


@POLICY_REGISTRY.register('masac')
class MASACPolicy(Policy):
    r"""
       Overview:
           Policy class of multi-agent SAC algorithm.

       Config:
           == ====================  ========    =============  ================================= =======================
           ID Symbol                Type        Default Value  Description                       Other(Shape)
           == ====================  ========    =============  ================================= =======================
           1  ``type``              str         td3            | RL policy register name, refer  | this arg is optional,
                                                               | to registry ``POLICY_REGISTRY`` | a placeholder
           2  ``cuda``              bool        True           | Whether to use cuda for network |
           3  | ``random_``         int         10000          | Number of randomly collected    | Default to 10000 for
              | ``collect_size``                               | training samples in replay      | SAC, 25000 for DDPG/
              |                                                | buffer when training starts.    | TD3.
           4  | ``model.policy_``   int         256            | Linear layer size for policy    |
              | ``embedding_size``                             | network.                        |
           5  | ``model.soft_q_``   int         256            | Linear layer size for soft q    |
              | ``embedding_size``                             | network.                        |
           6  | ``model.value_``    int         256            | Linear layer size for value     | Defalut to None when
              | ``embedding_size``                             | network.                        | model.value_network
              |                                                |                                 | is False.
           7  | ``learn.learning``  float       3e-4           | Learning rate for soft q        | Defalut to 1e-3, when
              | ``_rate_q``                                    | network.                        | model.value_network
              |                                                |                                 | is True.
           8  | ``learn.learning``  float       3e-4           | Learning rate for policy        | Defalut to 1e-3, when
              | ``_rate_policy``                               | network.                        | model.value_network
              |                                                |                                 | is True.
           9  | ``learn.learning``  float       3e-4           | Learning rate for policy        | Defalut to None when
              | ``_rate_value``                                | network.                        | model.value_network
              |                                                |                                 | is False.
           10 | ``learn.alpha``     float       0.2            | Entropy regularization          | alpha is initiali-
              |                                                | coefficient.                    | zation for auto
              |                                                |                                 | `\alpha`, when
              |                                                |                                 | auto_alpha is True
           11 | ``learn.repara_``   bool        True           | Determine whether to use        |
              | ``meterization``                               | reparameterization trick.       |
           12 | ``learn.``          bool        False          | Determine whether to use        | Temperature parameter
              | ``auto_alpha``                                 | auto temperature parameter      | determines the
              |                                                | `\alpha`.                       | relative importance
              |                                                |                                 | of the entropy term
              |                                                |                                 | against the reward.
           13 | ``learn.-``         bool        False          | Determine whether to ignore     | Use ignore_done only
              | ``ignore_done``                                | done flag.                      | in halfcheetah env.
           14 | ``learn.-``         float       0.005          | Used for soft update of the     | aka. Interpolation
              | ``target_theta``                               | target network.                 | factor in polyak aver
              |                                                |                                 | aging for target
              |                                                |                                 | networks.
           == ====================  ========    =============  ================================= =======================
       """

    config = dict(
        # (str) RL policy register name (refer to function "POLICY_REGISTRY").
        type='masac',
        # (bool) Whether to use cuda for network.
        cuda=False,
        # (bool type) on_policy: Determine whether on-policy or off-policy.
        # on-policy setting influences the behaviour of buffer.
        # Default False in SAC.
        on_policy=False,
        # (bool type) priority: Determine whether to use priority in buffer sample.
        # Default False in SAC.
        priority=False,
        # (bool) Whether use Importance Sampling Weight to correct biased update. If True, priority must be True.
        priority_IS_weight=False,
        # (int) Number of training samples(randomly collected) in replay buffer when training starts.
        # Default 10000 in SAC.
        random_collect_size=10000,
        model=dict(
            # (bool type) twin_critic: Determine whether to use double-soft-q-net for target q computation.
            # Please refer to TD3 about Clipped Double-Q Learning trick, which learns two Q-functions instead of one .
            # Default to True.
            twin_critic=True,

            # (bool type) value_network: Determine whether to use value network as the
            # original SAC paper (arXiv 1801.01290).
            # using value_network needs to set learning_rate_value, learning_rate_q,
            # and learning_rate_policy in `cfg.policy.learn`.
            # Default to False.
            # value_network=False,
        ),
        learn=dict(
            # (bool) Whether to use multi gpu
            multi_gpu=False,
            # How many updates(iterations) to train after collector's one collection.
            # Bigger "update_per_collect" means bigger off-policy.
            # collect data -> update policy-> collect data -> ...
            update_per_collect=1,
            # (int) Minibatch size for gradient descent.
            batch_size=256,

            # (float type) learning_rate_q: Learning rate for soft q network.
            # Default to 3e-4.
            # Please set to 1e-3, when model.value_network is True.
            learning_rate_q=3e-4,
            # (float type) learning_rate_policy: Learning rate for policy network.
            # Default to 3e-4.
            # Please set to 1e-3, when model.value_network is True.
            learning_rate_policy=3e-4,
            # (float type) learning_rate_value: Learning rate for value network.
            # `learning_rate_value` should be initialized, when model.value_network is True.
            # Please set to 3e-4, when model.value_network is True.
            learning_rate_value=3e-4,

            # (float type) learning_rate_alpha: Learning rate for auto temperature parameter `\alpha`.
            # Default to 3e-4.
            learning_rate_alpha=3e-4,
            # (float type) target_theta: Used for soft update of the target network,
            # aka. Interpolation factor in polyak averaging for target networks.
            # Default to 0.005.
            target_theta=0.005,
            # (float) discount factor for the discounted sum of rewards, aka. gamma.
            discount_factor=0.99,

            # (float type) alpha: Entropy regularization coefficient.
            # Please check out the original SAC paper (arXiv 1801.01290): Eq 1 for more details.
            # If auto_alpha is set  to `True`, alpha is initialization for auto `\alpha`.
            # Default to 0.2.
            alpha=0.2,

            # (bool type) auto_alpha: Determine whether to use auto temperature parameter `\alpha` .
            # Temperature parameter determines the relative importance of the entropy term against the reward.
            # Please check out the original SAC paper (arXiv 1801.01290): Eq 1 for more details.
            # Default to False.
            # Note that: Using auto alpha needs to set learning_rate_alpha in `cfg.policy.learn`.
            auto_alpha=True,
            # (bool type) log_space: Determine whether to use auto `\alpha` in log space.
            log_space=True,
            # (bool) Whether ignore done(usually for max step termination env. e.g. pendulum)
            # Note: Gym wraps the MuJoCo envs by default with TimeLimit environment wrappers.
            # These limit HalfCheetah, and several other MuJoCo envs, to max length of 1000.
            # However, interaction with HalfCheetah always gets done with done is False,
            # Since we inplace done==True with done==False to keep
            # TD-error accurate computation(``gamma * (1 - done) * next_v + reward``),
            # when the episode step is greater than max episode step.
            ignore_done=False,
            # (float) Weight uniform initialization range in the last output layer
            init_w=3e-3,
        ),
        collect=dict(
            # You can use either "n_sample" or "n_episode" in actor.collect.
            # Get "n_sample" samples per collect.
            # Default n_sample to 1.
            n_sample=1,
            # (int) Cut trajectories into pieces with length "unroll_len".
            unroll_len=1,
        ),
        eval=dict(),
        other=dict(
            replay_buffer=dict(
                # (int type) replay_buffer_size: Max size of replay buffer.
                replay_buffer_size=1000000,
                # (int type) max_use: Max use times of one data in the buffer.
                # Data will be removed once used for too many times.
                # Default to infinite.
                # max_use=256,
            ),
        ),
    )
    r"""
    Overview:
        Policy class of SAC algorithm.
    """

    def _init_learn(self) -> None:
        r"""
        Overview:
            Learn mode init method. Called by ``self.__init__``.
            Init q, value and policy's optimizers, algorithm config, main and target models.
        """
        # Init
        self._priority = self._cfg.priority
        self._priority_IS_weight = self._cfg.priority_IS_weight
        # self._value_network = False  # TODO self._cfg.model.value_network
        self._twin_critic = self._cfg.model.twin_critic

        # # Weight Init
        # init_w = self._cfg.learn.init_w
        # self._model.actor[2].weight.data.uniform_(-init_w, init_w)
        # self._model.actor[2].bias.data.uniform_(-init_w, init_w)
        # if self._twin_critic:
        #     self._model.critic[0][2].last.weight.data.uniform_(-init_w, init_w)
        #     self._model.critic[0][2].last.bias.data.uniform_(-init_w, init_w)
        #     self._model.critic[1][2].last.weight.data.uniform_(-init_w, init_w)
        #     self._model.critic[1][2].last.bias.data.uniform_(-init_w, init_w)
        # else:
        #     self._model.critic[2].last.weight.data.uniform_(-init_w, init_w)
        #     self._model.critic[2].last.bias.data.uniform_(-init_w, init_w)

        self._optimizer_q = Adam(
            self._model.critic.parameters(),
            lr=self._cfg.learn.learning_rate_q,
        )
        self._optimizer_policy = Adam(
            self._model.actor.parameters(),
            lr=self._cfg.learn.learning_rate_policy,
        )

        # Algorithm config
        self._gamma = self._cfg.learn.discount_factor
        # Init auto alpha
        if self._cfg.learn.auto_alpha:
            self._target_entropy = self._cfg.learn.get('target_entropy', -np.prod(self._cfg.model.action_shape))
            if self._cfg.learn.log_space:
                self._log_alpha = torch.log(torch.FloatTensor([self._cfg.learn.alpha]))
                self._log_alpha = self._log_alpha.to(self._device).requires_grad_()
                self._alpha_optim = torch.optim.Adam([self._log_alpha], lr=self._cfg.learn.learning_rate_alpha)
                assert self._log_alpha.shape == torch.Size([1]) and self._log_alpha.requires_grad
                self._alpha = self._log_alpha.detach().exp()
                self._auto_alpha = True
                self._log_space = True
            else:
                self._alpha = torch.FloatTensor([self._cfg.learn.alpha]).to(self._device).requires_grad_()
                self._alpha_optim = torch.optim.Adam([self._alpha], lr=self._cfg.learn.learning_rate_alpha)
                self._auto_alpha = True
                self._log_space = False
        else:
            self._alpha = torch.tensor(
                [self._cfg.learn.alpha], requires_grad=False, device=self._device, dtype=torch.float32
            )
            self._auto_alpha = False

        # Main and target models
        self._target_model = copy.deepcopy(self._model)
        self._target_model = model_wrap(
            self._target_model,
            wrapper_name='target',
            update_type='momentum',
            update_kwargs={'theta': self._cfg.learn.target_theta}
        )
        self._learn_model = model_wrap(self._model, wrapper_name='base')
        self._learn_model.reset()
        self._target_model.reset()

        self._forward_learn_cnt = 0

    def _forward_learn(self, data: dict) -> Dict[str, Any]:
        r"""
        Overview:
            Forward and backward function of learn mode.
        Arguments:
            - data (:obj:`dict`): Dict type data, including at least ['obs', 'action', 'reward', 'next_obs']
        Returns:
            - info_dict (:obj:`Dict[str, Any]`): Including current lr and loss.
        """
        loss_dict = {}
        data = default_preprocess_learn(
            data,
            use_priority=self._priority,
            use_priority_IS_weight=self._cfg.priority_IS_weight,
            ignore_done=self._cfg.learn.ignore_done,
            use_nstep=False
        )
        if self._cuda:
            data = to_device(data, self._device)

        self._learn_model.train()
        self._target_model.train()
        obs = data['obs']  # 'agent_state': (B,A,186), 'global_state': (B,A,389), 'action_mask': (B,A,16)
        next_obs = data['next_obs']
        reward = data['reward']  # (B,)
        done = data['done']  # (B,)
        logit = data['logit']  # (B,A,16)
        action = data['action']  # (B,A)

        # 1. predict q value
        q_value = self._learn_model.forward({'obs': obs}, mode='compute_critic')['q_value']
        dist = torch.distributions.categorical.Categorical(logits=logit)
        dist_entropy = dist.entropy()
        entropy = dist_entropy.mean()

        # 2. predict target value depend self._value_network.

        # target q value. SARSA: first predict next action, then calculate next q value
        with torch.no_grad():
            policy_output_next = self._learn_model.forward({'obs': next_obs}, mode='compute_actor')
            policy_output_next['logit'][policy_output_next['action_mask'] == 0.0] = -1e8
            prob = F.softmax(policy_output_next['logit'], dim=-1)
            log_prob = torch.log(prob + 1e-8)
            target_q_value = self._target_model.forward({'obs': next_obs}, mode='compute_critic')['q_value']
            # the value of a policy according to the maximum entropy objective
            if self._twin_critic:
                # find min one as target q value
                target_value = (prob * (
                            torch.min(target_q_value[0], target_q_value[1]) - self._alpha * log_prob.squeeze(-1))).sum(
                    dim=-1)
            else:
                target_value = (prob * (target_q_value - self._alpha * log_prob.squeeze(-1))).sum(
                    dim=-1)
        # target_value = target_q_value

        # 3. compute q loss
        if self._twin_critic:
            q_data0 = q_v_1step_td_data(q_value[0], target_value, action, reward, done, data['weight'])
            loss_dict['critic_loss'], td_error_per_sample0 = q_v_1step_td_error(q_data0, self._gamma)
            q_data1 = q_v_1step_td_data(q_value[1], target_value, action, reward, done, data['weight'])
            loss_dict['twin_critic_loss'], td_error_per_sample1 = q_v_1step_td_error(q_data1, self._gamma)
            td_error_per_sample = (td_error_per_sample0 + td_error_per_sample1) / 2
        else:
            q_data = q_v_1step_td_data(q_value, target_value, action, reward, done, data['weight'])
            loss_dict['critic_loss'], td_error_per_sample = q_v_1step_td_error(q_data, self._gamma)

        # 4. update q network
        self._optimizer_q.zero_grad()
        loss_dict['critic_loss'].backward()
        if self._twin_critic:
            loss_dict['twin_critic_loss'].backward()
        self._optimizer_q.step()

        # 5. evaluate to get action distribution
        policy_output = self._learn_model.forward({'obs': data['obs']}, mode='compute_actor')
        policy_output['logit'][policy_output['action_mask'] == 0.0] = -1e8
        logit = policy_output['logit']
        prob = F.softmax(logit, dim=-1)
        log_prob = torch.log(prob + 1e-8)

        with torch.no_grad():
            new_q_value = self._learn_model.forward({'obs': data['obs']}, mode='compute_critic')['q_value']
            if self._twin_critic:
                new_q_value = torch.min(new_q_value[0], new_q_value[1])  # (64,10,16)

        # 7. compute policy loss
        policy_loss = (prob * (self._alpha * log_prob - new_q_value.squeeze(-1))).sum(dim=-1).mean()

        loss_dict['policy_loss'] = policy_loss

        # 8. update policy network
        self._optimizer_policy.zero_grad()
        loss_dict['policy_loss'].backward()
        # grad_norm = torch.nn.utils.clip_grad_norm_(self._model.actor.parameters(), 10)  # TODO（pu）
        self._optimizer_policy.step()

        # 9. compute alpha loss
        if self._auto_alpha:
            if self._log_space:
                log_prob = log_prob + self._target_entropy
                loss_dict['alpha_loss'] = (-prob.detach() * (self._log_alpha * log_prob.detach())).sum(dim=-1).mean()

                self._alpha_optim.zero_grad()
                loss_dict['alpha_loss'].backward()
                self._alpha_optim.step()
                self._alpha = self._log_alpha.detach().exp()
            else:
                log_prob = log_prob + self._target_entropy
                loss_dict['alpha_loss'] = (-prob.detach() * (self._alpha * log_prob.detach())).sum(dim=-1).mean()

                self._alpha_optim.zero_grad()
                loss_dict['alpha_loss'].backward()
                self._alpha_optim.step()
                self._alpha = max(0, self._alpha)
                self._alpha.data = torch.where(self._alpha > 0, self._alpha, torch.zeros_like(self._alpha)).requires_grad_()

        loss_dict['total_loss'] = sum(loss_dict.values())

        info_dict = {}
        # if self._value_network:
        #    info_dict['cur_lr_v'] = self._optimizer_value.defaults['lr']

        # =============
        # after update
        # =============
        self._forward_learn_cnt += 1
        # target update
        self._target_model.update(self._learn_model.state_dict())
        return {
            'cur_lr_q': self._optimizer_q.defaults['lr'],
            'cur_lr_p': self._optimizer_policy.defaults['lr'],
            'priority': td_error_per_sample.abs().tolist(),
            'td_error': td_error_per_sample.detach().mean().item(),
            'alpha': self._alpha.item(),
            'q_value_1': target_q_value[0].detach().mean().item(),
            'q_value_2': target_q_value[1].detach().mean().item(),
            'target_value': target_value.detach().mean().item(),
            'entropy': entropy.item(),

            # 'policy_loss': loss_dict['policy_loss'].item(),
            # 'critic_loss': loss_dict['critic_loss'].item(),
            # 'twin_critic_loss': loss_dict['twin_critic_loss'].item(),
            **info_dict,
            **loss_dict
        }

    def _state_dict_learn(self) -> Dict[str, Any]:
        ret = {
            'model': self._learn_model.state_dict(),
            'optimizer_q': self._optimizer_q.state_dict(),
            'optimizer_policy': self._optimizer_policy.state_dict(),
        }
        # if self._value_network:
        #    ret.update({'optimizer_value': self._optimizer_value.state_dict()})
        if self._auto_alpha:
            ret.update({'optimizer_alpha': self._alpha_optim.state_dict()})
        return ret

    def _load_state_dict_learn(self, state_dict: Dict[str, Any]) -> None:
        self._learn_model.load_state_dict(state_dict['model'])
        self._optimizer_q.load_state_dict(state_dict['optimizer_q'])
        # if self._value_network:
        #    self._optimizer_value.load_state_dict(state_dict['optimizer_value'])
        self._optimizer_policy.load_state_dict(state_dict['optimizer_policy'])
        if self._auto_alpha:
            self._alpha_optim.load_state_dict(state_dict['optimizer_alpha'])

    def _init_collect(self) -> None:
        r"""
        Overview:
            Collect mode init method. Called by ``self.__init__``.
            Init traj and unroll length, collect model.
            Use action noise for exploration.
        """
        self._unroll_len = self._cfg.collect.unroll_len
        # self._collect_model = model_wrap(self._model, wrapper_name='multinomial_sample')  # TODO(pu)
        # self._collect_model = model_wrap(self._model, wrapper_name='eps_greedy_sample')
        self._collect_model = model_wrap(self._model, wrapper_name='eps_greedy_sample_masac')

        self._collect_model.reset()

    # def _forward_collect(self, data: dict) -> dict:
    #     r"""
    #     Overview:
    #         Forward function of collect mode.
    #     Arguments:
    #         - data (:obj:`dict`): Dict type data, including at least ['obs'].
    #     Returns:
    #         - output (:obj:`dict`): Dict type data, including at least inferred action according to input obs.
    #     """
    #     data_id = list(data.keys())
    #     data = default_collate(list(data.values()))
    #     if self._cuda:
    #         data = to_device(data, self._device)
    #     self._collect_model.eval()
    #     # print(data)
    #     with torch.no_grad():
    #         output = self._collect_model.forward({'obs': data}, mode='compute_actor')
    #     if self._cuda:
    #         output = to_device(output, 'cpu')
    #     output = default_decollate(output)
    #     # print(output)
    #     return {i: d for i, d in zip(data_id, output)}

    def _forward_collect(self, data: dict, eps: float) -> dict:
        r"""
        Overview:
            Forward function of collect mode.
        Arguments:
            - data (:obj:`dict`): Dict type data, including at least ['obs'].
        Returns:
            - output (:obj:`dict`): Dict type data, including at least inferred action according to input obs.
        """
        data_id = list(data.keys())
        data = default_collate(list(data.values()))
        if self._cuda:
            data = to_device(data, self._device)
        self._collect_model.eval()
        with torch.no_grad():
            # TODO(pu): eps_greedy_sample  eps_greedy_sample_masac
            output = self._collect_model.forward({'obs': data}, mode='compute_actor', eps=eps)
        if self._cuda:
            output = to_device(output, 'cpu')
        output = default_decollate(output)
        return {i: d for i, d in zip(data_id, output)}

    def _process_transition(self, obs: Any, model_output: dict, timestep: namedtuple) -> dict:
        r"""
        Overview:
            Generate dict type transition data from inputs.
        Arguments:
            - obs (:obj:`Any`): Env observation
            - model_output (:obj:`dict`): Output of collect model, including at least ['action']
            - timestep (:obj:`namedtuple`): Output after env step, including at least ['obs', 'reward', 'done'] \
                (here 'obs' indicates obs after env step, i.e. next_obs).
        Return:
            - transition (:obj:`Dict[str, Any]`): Dict type transition data.
        """
        transition = {
            'obs': obs,
            'next_obs': timestep.obs,
            'action': model_output['action'],
            'logit': model_output['logit'],
            'reward': timestep.reward,
            'done': timestep.done,
        }
        return transition

    def _get_train_sample(self, data: list) -> Union[None, List[Any]]:
        return get_train_sample(data, self._unroll_len)

    def _init_eval(self) -> None:
        r"""
        Overview:
            Evaluate mode init method. Called by ``self.__init__``.
            Init eval model. Unlike learn and collect model, eval model does not need noise.
        """
        self._eval_model = model_wrap(self._model, wrapper_name='argmax_sample')
        self._eval_model.reset()

    def _forward_eval(self, data: dict) -> dict:
        r"""
        Overview:
            Forward function for eval mode, similar to ``self._forward_collect``.
        Arguments:
            - data (:obj:`dict`): Dict type data, including at least ['obs'].
        Returns:
            - output (:obj:`dict`): Dict type data, including at least inferred action according to input obs.
        """
        data_id = list(data.keys())
        data = default_collate(list(data.values()))
        if self._cuda:
            data = to_device(data, self._device)
        self._eval_model.eval()
        with torch.no_grad():
            output = self._eval_model.forward({'obs': data}, mode='compute_actor')
        if self._cuda:
            output = to_device(output, 'cpu')
        output = default_decollate(output)
        return {i: d for i, d in zip(data_id, output)}

    def default_model(self) -> Tuple[str, List[str]]:
        return 'maqac', ['ding.model.template.maqac']

    def _monitor_vars_learn(self) -> List[str]:
        r"""
        Overview:
            Return variables' name if variables are to used in monitor.
        Returns:
            - vars (:obj:`List[str]`): Variables' name list.
        """
        twin_critic = ['twin_critic_loss'] if self._twin_critic else []
        if self._auto_alpha:
            return super()._monitor_vars_learn() + [
                'alpha_loss', 'policy_loss', 'critic_loss', 'cur_lr_q', 'cur_lr_p', 'target_q_value', 'q_value_1',
                'q_value_2', 'alpha', 'td_error', 'target_value', 'entropy'
            ] + twin_critic
        else:
            return super()._monitor_vars_learn() + [
                'policy_loss', 'critic_loss', 'cur_lr_q', 'cur_lr_p', 'target_q_value', 'q_value_1', 'q_value_2',
                'alpha', 'td_error', 'target_value', 'entropy'
            ] + twin_critic
