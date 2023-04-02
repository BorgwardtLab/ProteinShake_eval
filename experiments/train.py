import os
import argparse
import random
import copy
import numpy as np
import itertools
import pandas as pd

import hydra
from omegaconf import DictConfig, OmegaConf

import torch
from torch import nn
import torch.nn.functional as F
from torch.utils.data import Subset

from torch_geometric import utils
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader
import torch_geometric.transforms as T
from proteinshake.transforms import Compose

from proteinshake import tasks as ps_tasks
from proteinshake.tasks import __all__ as ALLTASKS

from proteinshake_eval.models.graph import GNN_TYPES
from proteinshake_eval.utils import get_cosine_schedule_with_warmup, get_task
from proteinshake_eval.utils import get_filter_mask
from proteinshake_eval.utils import get_data_loaders
from proteinshake_eval.utils import get_loss
from proteinshake_eval.metrics import compute_metrics
from proteinshake_eval.transforms import get_transformed_dataset
from proteinshake_eval.models.protein_model import ProteinStructureNet

import pytorch_lightning as pl


ALLTASKS = ALLTASKS[1:]


# def load_args():
#     parser = argparse.ArgumentParser(
#         description='PyTorch implementation of GNNs on Atom3d',
#         formatter_class=argparse.ArgumentDefaultsHelpFormatter
#     )

#     parser.add_argument('--representation', type=str, default='graph',
#                         help='representation (graph/voxel/point)')
#     parser.add_argument('--seed', type=int, default=0,
#                         help='random seed')
#     parser.add_argument('--dataset', type=str, default=ALLTASKS[0], choices=ALLTASKS,
#                         help='which dataset')
#     parser.add_argument('--debug', action='store_true',
#                         help='debug mode using escherichia_coli subset')

#     # Representation hyperparameters
#     parser.add_argument('--graph-eps', type=float, default=8.0,
#                         help='constructing eps graphs from distance matrices')
#     parser.add_argument('--voxelsize', type=int, default=10, help="size of the voxels")
#     parser.add_argument('--gridsize', type=int, default=10, help="size of the voxel grid")

#     # Model hyperparameters
#     parser.add_argument('--num-layers', type=int, default=5, help="number of layers")
#     parser.add_argument('--kernel-size', type=int, default=3, help="kernel size")
#     parser.add_argument('--embed-dim', type=int, default=256, help="hidden dimensions")
#     parser.add_argument('--dropout', type=float, default=0.0, help="dropout")
#     parser.add_argument('--gnn-type', type=str, default='gin', choices=GNN_TYPES,
#                         help='gnn type')
#     parser.add_argument('--use-edge-attr', action='store_true', help='use edge features')
#     parser.add_argument('--pooling', type=str, default='mean', help='global pooling')
#     parser.add_argument('--pe', type=str, default=None, choices=['None', 'learned', 'sine'])
#     parser.add_argument('--out-head', type=str, default='linear', choices=['linear', 'mlp'])
#     parser.add_argument('--pretrained', type=str, default=None, help='pretrained model path')
#     parser.add_argument('--aggregation', type=str, default='dot', choices=['dot', 'concat', 'sum'])
#     parser.add_argument('--aggregation-norm', action='store_true', help='normalize before aggregation')
#     parser.add_argument('--alpha', type=float, default=0.001, help="regularization coef for point clouds")

#     # Optimization hyperparameters
#     parser.add_argument('--epochs', type=int, default=100, help='number of epochs')
#     parser.add_argument('--lr', type=float, default=0.001,
#                         help='initial learning rate')
#     parser.add_argument('--weight-decay', type=float, default=1e-06, help='weight decay')
#     parser.add_argument('--batch-size', type=int, default=256,
#                         help='batch size')
#     parser.add_argument('--warmup', type=int, default=10, help='warmup epochs')
#     parser.add_argument('--scale', action='store_true', help='rescale y')

#     # Other hyperparameters
#     parser.add_argument('--outdir', type=str, default='../logs', help='out path')
#     parser.add_argument('--num-workers', type=int, default=0,
#                         help='number of workers for loader')
#     args = parser.parse_args()

#     args.pe = None if args.pe == 'None' else args.pe

#     if args.debug:
#         args.epochs = 10
#         args.embed_dim = 16
#         args.num_layers = 2
#         args.outdir = '../logs_debug'

#     if args.representation == 'point':
#         args.pooling = 'max'

#     if args.dataset == 'binding_site':
#         args.pooling = None

#     args.save_logs = False
#     if args.outdir != '':
#         args.save_logs = True
#         if args.representation == 'graph':
#             if args.pretrained is None:
#                 outdir = args.outdir + '/{}'.format(args.dataset)
#                 outdir = outdir + '/{}_{}'.format(args.lr, args.weight_decay)
#                 outdir = outdir + '/{}_{}_{}_{}_{}_{}_{}_{}'.format(
#                     args.pooling, args.out_head, args.gnn_type, args.num_layers,
#                     args.embed_dim, args.dropout, args.use_edge_attr, args.pe
#                 )
#             else:
#                 outdir = args.pretrained + '/{}'.format(args.dataset)
#                 outdir = outdir + '/{}_{}'.format(args.lr, args.weight_decay)
#                 outdir = outdir + '/{}_{}_{}'.format(
#                     args.pooling, args.out_head, args.dropout
#                 )
#             if args.dataset in ['ligand_affinity']:
#                 outdir = outdir + '/{}'.format(args.aggregation)
#         elif args.representation == 'voxel':
#             if args.pretrained is None:
#                 outdir = f'{args.outdir}/{args.dataset}/{args.lr}_{args.weight_decay}/{args.kernel_size}_{args.num_layers}_{args.embed_dim}_{args.dropout}_{args.voxelsize}_{args.gridsize}'
#             else:
#                 outdir = f'{args.pretrained}/{args.dataset}/{args.lr}_{args.weight_decay}/{args.kernel_size}_{args.num_layers}_{args.embed_dim}_{args.dropout}_{args.voxelsize}_{args.gridsize}'
#         elif args.representation == 'point':
#             if args.pretrained is None:
#                 outdir = args.outdir + '/{}'.format(args.dataset)
#                 outdir = outdir + '/{}_{}'.format(args.lr, args.weight_decay)
#                 outdir = outdir + '/{}_{}_{}'.format(
#                     args.pooling, args.embed_dim, args.alpha
#                 )
#             else:
#                 outdir = args.pretrained + '/{}'.format(args.dataset)
#                 outdir = outdir + '/{}_{}'.format(args.lr, args.weight_decay)
#                 outdir = outdir + '/{}_{}'.format(
#                     args.pooling, args.alpha
#                 )

#         os.makedirs(outdir, exist_ok=True)
#         args.outdir = outdir

#     torch.manual_seed(args.seed)
#     np.random.seed(args.seed)
#     random.seed(args.seed)
#     if torch.cuda.is_available():
#         torch.cuda.manual_seed_all(args.seed)
#     return args

class ProteinTaskTrainer(pl.LightningModule):
    def __init__(self, model, cfg, task, y_transform=None):
        super().__init__()
        self.model = model
        self.cfg = cfg
        self.task = task
        # if 'multi_class' in task.task_type:
        #     self.main_metric = 'acc'
        #     self.criterion = nn.CrossEntropyLoss()
        #     self.best_val_score = 0.0
        # elif task.task_type == 'binary-classification':
        #     self.main_metric = 'auc'
        #     self.criterion = nn.BCEWithLogitsLoss()
        #     self.best_val_score = 0.0
        # elif task.task_type == 'regression':
        #     self.main_metric = 'neg_mse'
        #     #self.criterion = nn.MSELoss()
        #     self.criterion = nn.L1Loss()
        #     self.best_val_score = -float('inf')
        # else:
        #     raise ValueError("Unknown task type!")
        self.criterion, self.main_metric = get_loss(task.task_type[1])
        self.best_val_score = -float('inf')
        self.main_val_metric = 'val_' + self.main_metric
        self.best_weights = None
        self.y_transform = y_transform

    def inverse_transform(self, y_true, y_pred):
        if self.y_transform is None:
            return y_true, y_pred
        return self.y_transform.inverse_transform(y_true), self.y_transform.inverse_transform(y_pred)

    def training_step(self, batch, batch_idx):
        y_hat, y = self.model.step(batch)
        loss = self.criterion(y_hat, y)
        if hasattr(self.model, "regularizer_loss"):
            reg_loss = self.model.regularizer_loss(self.cfg.alpha)
            loss = loss + reg_loss

        if 'classification' in self.task.task_type:
            if 'binary' in self.task.task_type:
                acc = ((y_hat.detach() > 0).float() == y).float().mean().item()
                self.log("train_acc", acc, on_step=False, on_epoch=True, batch_size=1, prog_bar=True)
            else:
                acc = (y_hat.detach().argmax(dim=-1) == y).float().mean().item()
                self.log("train_acc", acc, on_step=False, on_epoch=True, batch_size=1, prog_bar=True)
        self.log("train_loss", loss, on_step=False, on_epoch=True, batch_size=1)

        return loss

    def validation_step(self, batch, batch_idx):
        y_hat, y = self.model.step(batch)
        loss = self.criterion(y_hat, y)

        self.log('val_loss', loss, batch_size=len(y))
        return {'y_pred': y_hat, 'y_true': y}

    def evaluate_epoch_end(self, outputs, stage='val'):
        all_preds = torch.vstack([out['y_pred'] for out in outputs])
        all_true = torch.cat([out['y_true'] for out in outputs])
        all_true, all_preds = all_true.cpu().numpy(), all_preds.cpu().numpy()
        all_true, all_preds = self.inverse_transform(all_true, all_preds)
        scores = compute_metrics(all_true, all_preds, self.task)
        # scores = self.task.evaluate(all_true, all_preds)
        scores = {'{}_'.format(stage) + str(key): val for key, val in scores.items()}
        if stage == 'val':
            self.log_dict(scores)
        return scores

    def validation_epoch_end(self, outputs):
        scores = self.evaluate_epoch_end(outputs, 'val')
        if scores[self.main_val_metric] >= self.best_val_score:
            self.best_val_score = scores[self.main_val_metric]
            self.best_weights = copy.deepcopy(self.model.state_dict())
        return scores

    def test_step(self, batch, batch_idx):
        y_hat, y = self.model.step(batch)
        loss = self.criterion(y_hat, y)
        return {'y_pred': y_hat, 'y_true': y}

    def test_epoch_end(self, outputs):
        scores = self.evaluate_epoch_end(outputs, 'test')
        scores['best_val_score'] = self.best_val_score
        df = pd.DataFrame.from_dict(scores, orient='index')
        df.to_csv(f"{self.logger.log_dir}/results.csv",
                  header=['value'], index_label='name')
        return scores

    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.cfg.training.lr,
            weight_decay=self.cfg.training.weight_decay
        )
        lr_scheduler = get_cosine_schedule_with_warmup(
            optimizer, self.cfg.training.warmup, self.cfg.training.epochs
        )
        return [optimizer], [lr_scheduler]

    def plot(self):
        import matplotlib.pyplot as plt
        plt.switch_backend("agg")
        import seaborn as sns
        metrics = pd.read_csv(f"{self.logger.log_dir}/metrics.csv")
        del metrics["step"]
        metrics.set_index("epoch", inplace=True)
        if 'classification' in self.task.task_type:
            metric_list = ['val_acc', 'val_loss', 'train_acc', 'train_loss']
        elif 'regression' in self.task.task_type:
            metric_list = ['val_mse', 'val_mae', 'val_loss', 'train_loss']
        metrics = metrics[metric_list]
        sns.relplot(data=metrics, kind="line")
        plt.savefig(self.logger.log_dir + '/plot.png')
        plt.close()


@hydra.main(version_base="1.3", config_path="../config", config_name="config")
def main(cfg: DictConfig) -> None:
    print(OmegaConf.to_yaml(cfg))
    pl.seed_everything(cfg.general.seed, workers=True)
    # return
    # global args
    # args = load_args()
    # print(args)

    # datapath = "../data/{}".format(args.dataset)
    # args.pair_prediction = False
    # args.same_type = False
    # args.other_dim = None
    # y_transform = None
    # task = get_task(args.dataset)(root=datapath, verbosity=1, split='random')
    task = get_task(cfg.task.class_name)(
        root=cfg.task.path, split=cfg.task.split, verbosity=1)
    dset = task.dataset
    # num_class = task.num_classes

    # if args.dataset == 'ec':
    #     task = ps_tasks.EnzymeClassTask(root=datapath, verbosity=1, split='random')
    #     dset = task.dataset
    #     num_class = task.num_classes
    # elif args.dataset == 'ligand_affinity':
    #     task = ps_tasks.LigandAffinityTask(root=datapath)
    #     # normalize y
    #     dset = task.dataset
    #     num_class = 1
    #     args.pair_prediction = True
    #     args.same_type = False
    #     if args.scale:
    #         from sklearn.preprocessing import StandardScaler
    #         all_y = np.asarray([
    #             task.target(protein_dict) for protein_dict in dset.proteins()[0]])[task.train_ind]
    #         y_transform = StandardScaler().fit(all_y.reshape(-1, 1))
    # elif args.dataset == 'binding_site':
    #     task = ps_tasks.BindingSitePredictionTask(root=datapath)
    #     dset = task.dataset
    #     num_class = 1
    # elif args.dataset == 'scop':
    #     task = ps_tasks.SCOPTask(root=datapath, scop_level='SCOP-CL')
    #     dset = task.dataset
    #     num_class = task.num_classes

    # else:
    #     raise ValueError("not implemented!")

    # protein_len_list = np.asarray([len(protein_dict['protein']['sequence']) for protein_dict in dset.proteins()])
    # print("Protein length less or equal to 3000 is {}%".format(
    #     np.sum(protein_len_list <= 3000) / len(protein_len_list) * 100))
    # train_mask = protein_len_list[task.train_index] <= 3000
    # val_mask = protein_len_list[task.val_index] <= 3000
    # test_mask = protein_len_list[task.test_index] <= 3000

    # filter proteins longer than 3000
    index_masks = get_filter_mask(dset, task, 3000)

    y_transform = None
    if task.task_type[1] == 'regression':
        from sklearn.preprocessing import StandardScaler
        all_y = np.asarray([
            task.target(protein_dict) for protein_dict in dset.proteins()])[task.train_index]
        y_transform = StandardScaler().fit(all_y.reshape(-1, 1))

    # data_transform = get_train_transform(args, task, y_transform)
    # dset = dset.to
    dset = get_transformed_dataset(cfg.representation, dset, task, y_transform)
    task.other_dim = dset[0].other_x.shape[-1] if cfg.task.name == 'ligand_affinity' else None 
    net = ProteinStructureNet(cfg.model, task)


    # if args.representation == 'graph':
    #     from proteinshake_eval.transforms.graph import TrainingAttr
    #     dset = dset.to_graph(eps=args.graph_eps).pyg(
    #         transform=TrainingAttr(task, y_transform)
    #     )
    #     if args.dataset == 'ligand_affinity':
    #         args.other_dim = dset[0].other_x.shape[-1]
    #     from proteinshake_eval.models.graph import GNN_graphpred
    #     net = GNN_graphpred(
    #         num_class,
    #         args.embed_dim,
    #         args.num_layers,
    #         args.dropout,
    #         args.gnn_type,
    #         args.use_edge_attr,
    #         args.pe,
    #         args.pooling,
    #         args.out_head,
    #         args.pair_prediction,
    #         args.same_type,
    #         args.other_dim,
    #         args.aggregation,
    #         args.aggregation_norm
    #     )
    # elif args.representation == 'voxel':
    #     from transforms.voxel import VoxelRotationAugment
    #     if args.dataset == 'ec':
    #         from transforms.voxel import VoxelEnzymeClassTransform as Transform
    #         from models.voxel import VoxelNet_EnzymeClass as VoxelNet
    #     elif args.dataset == 'ligand_affinity':
    #         from transforms.voxel import VoxelLigandAffinityTransform as Transform
    #         from models.voxel import VoxelNet_LigandAffinity as VoxelNet
    #     elif args.dataset == 'scop':
    #         from transforms.voxel import VoxelScopTransform as Transform
    #         from models.voxel import VoxelNet_Scop as VoxelNet
    #     dset = dset.to_voxel(gridsize=(args.gridsize, args.gridsize, args.gridsize), voxelsize=args.voxelsize).torch(
    #         transform=Compose([VoxelRotationAugment(),Transform(task, y_transform=y_transform)])
    #     )
    #     if args.dataset == 'ligand_affinity':
    #         args.other_dim = dset[0][2].shape[-1]
    #     net = VoxelNet(
    #         input_dim = 20,
    #         out_dim = num_class,
    #         hidden_dim = args.embed_dim,
    #         num_layers = args.num_layers,
    #         kernel_size = args.kernel_size,
    #         dropout = args.dropout,
    #         other_dim = args.other_dim
    #     )
    # elif args.representation == 'point':
    #     from transforms.point import PointTrainingTransform as Transform
    #     from models.point import PointNet_pred
    #     max_len = np.max(protein_len_list[protein_len_list <= 1000])
    #     dset = dset.to_point().torch(transform=Transform(task, y_transform=y_transform, max_len=max_len))
    #     if args.dataset == 'ligand_affinity':
    #         args.other_dim = dset[0].other_x.shape[-1]
    #     net = PointNet_pred(
    #         num_class,
    #         args.embed_dim,
    #         global_pool=args.pooling,
    #         out_head=args.out_head,
    #         pair_prediction=args.pair_prediction,
    #         same_type=args.same_type,
    #         other_dim=args.other_dim,
    #         aggregation=args.aggregation)
    # else:
    #     raise ValueError("Not implemented representation!")

    train_loader, val_loader, test_loader = get_data_loaders(
        dset, task, index_masks,
        cfg.training.batch_size, cfg.training.num_workers
    )

    # train_loader = DataLoader(Subset(dset, np.asarray(task.train_index)[train_mask]), batch_size=args.batch_size,
    #                           shuffle=True, num_workers=args.num_workers)
    # val_loader = DataLoader(Subset(dset, np.asarray(task.val_index)[val_mask]), batch_size=args.batch_size,
    #                           shuffle=False, num_workers=args.num_workers)
    # test_loader = DataLoader(Subset(dset, np.asarray(task.test_index)[test_mask]), batch_size=args.batch_size,
    #                           shuffle=False, num_workers=args.num_workers)

    if cfg.model.pretrained is not None:
        print("Loading pretrained model...")
        net.from_pretrained(cfg.model.pretrained + '/model.pt')

    model = ProteinTaskTrainer(net, cfg, task, y_transform)

    logger = pl.loggers.CSVLogger(cfg.paths.output_dir, name='csv_logs')
    callbacks = [
        pl.callbacks.LearningRateMonitor(),
        pl.callbacks.TQDMProgressBar(refresh_rate=1000)
    ]

    limit_train_batches = 5 if cfg.training.debug else None
    limit_val_batches = 5 if cfg.training.debug else None
    # enable_checkpointing = False if args.debug else True
    trainer = pl.Trainer(
        limit_train_batches=limit_train_batches,
        limit_val_batches=limit_val_batches,
        max_epochs=cfg.training.epochs,
        devices='auto',
        accelerator='auto',
        enable_checkpointing=False,
        # default_root_dir=args.outdir,
        logger=[logger],
        callbacks=callbacks
    )

    trainer.fit(model, train_loader, val_loader)
    model.model.load_state_dict(model.best_weights)
    model.best_weights = None
    trainer.test(model, test_loader)
    # model.plot()
    # if args.save_logs:
    #     net.save(args.outdir + '/model.pt', args)


if __name__ == "__main__":
    main()
