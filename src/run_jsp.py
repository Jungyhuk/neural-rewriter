# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
#

import argparse
import math
import random
import sys
import os
import json
import numpy as np
import time

import torch
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.sampler import RandomSampler, SequentialSampler

import arguments
import models
import models.data_utils.data_utils as data_utils
import models.model_utils as model_utils
from models.jspModel import jspModel


def create_model(args, term_vocab=None, term_vocab_list=None, op_vocab=None, op_vocab_list=None):
	args.embedding_size = args.num_res * (args.max_job_len + 1) + 1
	model = jspModel(args)
	
	if model.cuda_flag:
		model = model.cuda()
	model.share_memory()
	model_supervisor = model_utils.jspSupervisor(model, args)
	if args.load_model:
		model_supervisor.load_pretrained(args.load_model)
	else:
		print('Created model with fresh parameters.')
		model_supervisor.model.init_weights(args.param_init)
	return model_supervisor


def train(args):
	print('Training:')
	
	train_data = data_utils.load_dataset(args.train_dataset, args)
	train_data_size = len(train_data)
	if args.train_proportion < 1.0:
		random.shuffle(train_data)
		train_data_size = int(train_data_size * args.train_proportion)
		train_data = train_data[:train_data_size]

	eval_data = data_utils.load_dataset(args.val_dataset, args)
	
	DataProcessor = data_utils.jspDataProcessor(args)
	model_supervisor = create_model(args)

	logger = model_utils.Logger(args)

	for epoch in range(args.num_epochs):
		random.shuffle(train_data)
		for batch_idx in range(0, train_data_size, args.batch_size):
			print(epoch, batch_idx)
			batch_data = DataProcessor.get_batch(train_data, args.batch_size, batch_idx)
			train_loss, train_reward = model_supervisor.train(batch_data)
			print('train loss: %.4f train reward: %.4f' % (train_loss, train_reward))

			if model_supervisor.global_step % args.eval_every_n == 0:
				eval_loss, eval_reward = model_supervisor.eval(eval_data, args.output_trace_flag, args.max_eval_size)
				val_summary = {'avg_reward': eval_reward}
				model_supervisor.save_model()
				val_summary['global_step'] = model_supervisor.global_step
				logger.write_summary(val_summary)

			if args.lr_decay_steps is not None and model_supervisor.global_step % args.lr_decay_steps == 0:
				model_supervisor.model.lr_decay(args.lr_decay_rate)
				if model_supervisor.model.cont_prob > 0.01:
					model_supervisor.model.cont_prob *= 0.5


def evaluate(args):
	print('Evaluation:')

	test_data = data_utils.load_dataset(args.test_dataset, args)
	test_data_size = len(test_data)
	args.dropout_rate = 0.0

	dataProcessor = data_utils.jspDataProcessor(args)
	model_supervisor = create_model(args)
	test_loss, test_reward = model_supervisor.eval(test_data, args.output_trace_flag)
	

	print('test loss: %.4f test reward: %.4f' % (test_loss, test_reward))


if __name__ == "__main__":
	argParser = arguments.get_arg_parser("jsp")
	args = argParser.parse_args()
	args.cuda = not args.cpu and torch.cuda.is_available()
	random.seed(args.seed)
	np.random.seed(args.seed)
	if args.eval:
		evaluate(args)
	else:
		train(args)

