import os
from distutils.util import strtobool
from enum import Enum

import torch


try:
    import torch_xla.core.xla_model as xm

    _tpu_available = True
except ImportError:
    _tpu_available = False


def is_tpu_available():
    return _tpu_available


def parse_flag_from_env(key, default=False):
    value = os.environ.get(key, str(default))
    return strtobool(value) == 1  # As its name indicates `strtobool` actually returns an int...


class DistributedType(str, Enum):
    # Subclassing str as well as Enum allows the `DistributedType` to be JSON-serializable out of the box.
    NO = "NO"
    MULTI_GPU = "MULTI_GPU"
    TPU = "TPU"


# Inspired by Alex Martelli's 'Borg'.
class AcceleratorState:
    """
    This is a variation of a `singleton class <https://en.wikipedia.org/wiki/Singleton_pattern>`__ in the sense that
    all instance of :obj:`AcceleratorState` share the same state, which is initialized on the first instantiation.
    """

    _shared_state = {}

    def __init__(self, fp16: bool = None, cpu: bool = False, _from_accelerator: bool = False):
        self.__dict__ = self._shared_state
        if not getattr(self, "initialized", False):
            if not _from_accelerator:
                raise ValueError(
                    "Please make sure to properly initialize your accelerator via `accelerator = Accelerator()` "
                    "before using any functionality from the `accelerate` library."
                )
            elif is_tpu_available() and not cpu:
                self.distributed_type = DistributedType.TPU
                self.num_processes = xm.xrt_world_size()
                self.process_index = xm.get_ordinal()
                self.local_process_index = xm.get_local_ordinal()
                self.device = xm.xla_device()
                self.use_fp16 = False
            elif int(os.environ.get("LOCAL_RANK", -1)) != -1 and not cpu:
                self.distributed_type = DistributedType.MULTI_GPU
                if not torch.distributed.is_initialized():
                    torch.distributed.init_process_group(backend="nccl")
                self.num_processes = torch.distributed.get_world_size()
                self.process_index = torch.distributed.get_rank()
                self.local_process_index = int(os.environ.get("LOCAL_RANK", -1))
                self.device = torch.device("cuda", self.local_process_index)
                self.use_fp16 = parse_flag_from_env("USE_FP16", False) if fp16 is None else fp16
            else:
                self.distributed_type = DistributedType.NO
                self.num_processes = 1
                self.process_index = self.local_process_index = 0
                self.device = torch.device("cuda" if torch.cuda.is_available() and not cpu else "cpu")
                self.use_fp16 = parse_flag_from_env("USE_FP16", False) if fp16 is None else fp16
            self.initialized = True

    def __repr__(self):
        return (
            f"Distributed environment: {self.distributed_type}\n"
            f"Num processes: {self.num_processes}\n"
            f"Process index: {self.process_index}\n"
            f"Local process index: {self.local_process_index}\n"
            f"Device: {self.device}\n"
            f"Use FP16 precision: {self.use_fp16}\n"
        )
