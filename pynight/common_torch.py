import torch
import torch.nn as nn
import torchvision
import functools
from contextlib import nullcontext
import socket
import psutil
import humanize
import time
import matplotlib.pyplot as plt
import gc
from .common_jupyter import jupyter_gc
from .common_numpy import hash_array_np
from pynight.common_files import rm

try:
    import jax
except ImportError:
    pass

try:
    from codecarbon import OfflineEmissionsTracker
except ImportError:
    pass


##
def torch_shape_get(input, size_p=False, type_only_p=False):
    total_size = 0

    def h_shape_get(x):
        nonlocal total_size

        res = ()
        if hasattr(x, "dtype"):
            res += (x.dtype,)
            if hasattr(x, "shape"):
                res += (x.shape,)

        elif hasattr(x, "shape"):
            res += (type(x), x.shape)

        if size_p and hasattr(x, "element_size") and hasattr(x, "nelement"):
            size = torch_memory_tensor(x, s=2)
            total_size += size

            res += (f"{size:.2f}MB",)

        if len(res) == 0:
            if type_only_p:
                res = type(x)
            else:
                res = x

        return res

    res = jax.tree_map(h_shape_get, input)

    if size_p:
        # return (f"total_size: {total_size:.2f}MB", res)
        return dict(total_size_mb=total_size, tree=res)
    else:
        return res


##
class TorchModelMode:
    """
    A context manager to temporarily set a PyTorch model's mode to either training or evaluation, and restore its
    original mode when exiting the context.

    Args:
        model (torch.nn.Module): The PyTorch model whose mode needs to be temporarily set.
        mode (str): The mode to set the model to within the context. Must be either 'train' or 'eval'.

    Example:
        model = nn.Linear(10, 5)  # A simple PyTorch model for demonstration

        with TorchModelMode(model, 'eval'):
            # The model is in evaluation mode within this block
            pass

        # The model is back to its original mode after the block
    """

    def __init__(self, model: nn.Module, mode: str):
        self.model = model
        self.mode = mode
        self.original_mode = None

    def __enter__(self):
        self.original_mode = self.model.training  # Save the original mode
        if self.mode.lower() == "train":
            self.model.train()
        elif self.mode.lower() == "eval":
            self.model.eval()
        else:
            raise ValueError(f"Invalid mode '{self.mode}', must be 'train' or 'eval'")

    def __exit__(self, exc_type, exc_value, traceback):
        if self.original_mode:  # Restore the original mode
            self.model.train()
        else:
            self.model.eval()


##
torch_to_PIL = torchvision.transforms.ToPILImage()


def img_tensor_show(img_tensor):
    plt.imshow(torch_to_PIL(img_tensor))
    plt.show()


##
def torch_gpu_memory_stats():
    #: @seeAlso `print(torch.cuda.memory_summary())`
    ###
    gigabyte = 1024**3

    allocated = torch.cuda.memory_allocated() / (gigabyte)
    reserved = torch.cuda.memory_reserved() / (gigabyte)
    print(f"gpu allocated: {allocated}\ngpu reserved: {reserved}")


def torch_memory_tensor(tensor, s=3):
    #: s=3: gigabyte
    ##
    size_in_bytes = tensor.element_size() * tensor.nelement()
    size = size_in_bytes / (1024**s)
    return size


def torch_gpu_empty_cache():
    jupyter_gc()
    gc.collect()
    torch.cuda.empty_cache()


def torch_gpu_remove_all():
    #: This does not remove all GPU tensors. I don't know why. I think it's because `del obj` is not actually deleting the tensors.
    #: [[id:68188d07-4317-412f-ab74-bd3158e2a378][How do I forcefully release the memory of a tensor? - PyTorch Forums]]
    #:
    #: * [[https://docs.python.org/3/library/gc.html][gc — Garbage Collector interface — Python 3.11.3 documentation]]
    #: ** =gc.get_objects=
    #: Returns a list of all objects tracked by the collector, excluding the list returned. If generation is not None, return only the objects tracked by the collector that are in that generation.
    ##
    for obj in gc.get_objects():
        try:
            if torch.is_tensor(obj) or (
                hasattr(obj, "data") and torch.is_tensor(obj.data)
            ):
                if obj.is_cuda:
                    del obj
        except:
            #: There are errors when trying to determine if these objects are tensors or not.
            pass

    torch_gpu_empty_cache()


##
def no_grad_maybe(no_grad_p):
    #: @seeAlso `torch.set_grad_enabled(mode=False)`
    ##
    if no_grad_p:
        return torch.no_grad()
    else:
        return nullcontext()


##
def model_device_get(model):
    return next(model.parameters()).device


##
def hash_tensor(tensor, *args, **kwargs):
    return hash_array_np(tensor.cpu().numpy(), *args, **kwargs)


##
def prepend_value(tensor: torch.Tensor, value) -> torch.Tensor:
    """
    Returns a tensor which is the input tensor with `value` prepended to its last dimension.

    Args:
        tensor (torch.Tensor): The input tensor.
        value: The value to prepend.

    Returns:
        torch.Tensor: The output tensor `value` prepended to its last dimension.

    Example:
        >>> tensor = torch.tensor([[2, 2, 3], [4, 5, 6]])
        >>> prepend_value(tensor, 33)
        tensor([[33,  2,  2,  3],
                [33,  4,  5,  6]])
    """
    device = tensor.device

    filler = torch.full(
        (*tensor.shape[:-1], 1), fill_value=value, dtype=tensor.dtype, device=device
    )
    return torch.cat((filler, tensor), dim=-1)


##
def drop_tokens(
    tokens: torch.Tensor,
    mask: torch.Tensor,
    num_prefix_tokens: int = 1,
    ordered: bool = True,
) -> torch.Tensor:
    """
    Drops tokens according to the given mask and preserves the prefix tokens.

    Parameters:
    tokens: [batch, token, hidden]
        The tokens to drop.
    mask: [batch, token]
        The mask indicating which tokens to keep.
    num_prefix_tokens: int, default = 1
        The number of prefix tokens to keep.
    ordered: bool, default = True
        Whether to keep the order of the tokens or not.

    Returns:
    torch.Tensor
        The tensor with dropped tokens.

    Example:
    ```
    import torch
    from icecream import ic

    tokens = torch.randint(low=0, high=100, size=(2, 5, 10))

    mask = torch.tensor([[True, False, False, True], [False, True, True, False]], dtype=torch.int64)
    ic(mask.shape)

    dropped_tokens = drop_tokens(tokens, mask, num_prefix_tokens=1, ordered=True)
    ic(dropped_tokens.shape)

    print(tokens)
    print(mask)
    print(dropped_tokens)
    ```
    This would output:
    ```
    ic| mask.shape: torch.Size([2, 4])
    ic| dropped_tokens.shape: torch.Size([2, 3, 10])
    tensor([[[16, 65, 37, 10, 71, 13, 59, 62, 78, 91],
             [72, 76, 57, 34, 76, 91, 61,  2, 66, 28],
             [22, 92,  8, 14, 93, 12, 45, 54, 27, 38],
             [13, 37,  3, 56, 85, 24,  9, 22, 14, 97],
             [69,  3, 49, 42, 80, 82,  8, 74, 21, 67]],

            [[24, 33, 32, 39,  6, 89, 96, 90, 65, 79],
             [80,  8, 86, 93, 34, 86,  9, 75, 63, 78],
             [61, 89, 57, 55,  2, 84, 59, 65, 95, 23],
             [31, 49, 97, 28, 23, 69, 96, 58, 46, 59],
             [59, 15, 33, 29, 90, 59, 35, 16, 56, 73]]])
    tensor([[1, 0, 0, 1],
            [0, 1, 1, 0]])
    tensor([[[16, 65, 37, 10, 71, 13, 59, 62, 78, 91],
             [72, 76, 57, 34, 76, 91, 61,  2, 66, 28],
             [69,  3, 49, 42, 80, 82,  8, 74, 21, 67]],

            [[24, 33, 32, 39,  6, 89, 96, 90, 65, 79],
             [61, 89, 57, 55,  2, 84, 59, 65, 95, 23],
             [31, 49, 97, 28, 23, 69, 96, 58, 46, 59]]])
    ```
    """

    if num_prefix_tokens:
        prefix_tokens, tokens = (
            tokens[:, :num_prefix_tokens],
            tokens[:, num_prefix_tokens:],
        )
    else:
        prefix_tokens = None

    assert tokens.shape[:-1] == mask.shape

    tokens_shape = tokens.shape
    # ic(tokens_shape)

    tokens = tokens[mask.nonzero(as_tuple=True)]
    tokens = tokens.reshape((tokens_shape[0], -1, *tokens_shape[2:]))
    #: @assumption For all i, `mask[i].sum()` is constant.

    # ic(tokens.shape)

    if prefix_tokens is not None:
        # ic(prefix_tokens.shape)

        tokens = torch.cat((prefix_tokens, tokens), dim=1)

    return tokens


##
def torch_device_name_get(device=None):
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(device=device)
    else:
        device_name = "cpu"

    return device_name


##
def host_info_get(device=None):
    metadata = dict()

    device_name = torch_device_name_get(device=device)

    hostname = socket.gethostname()

    total_ram = psutil.virtual_memory().total
    total_ram_gb = total_ram // (1024**3)
    #: converts bytes to gigabytes

    metadata["device_name"] = device_name
    metadata["total_ram_gb"] = total_ram_gb
    metadata["hostname"] = hostname

    try:
        device_properties = torch.cuda.get_device_properties(device)
        device_properties_dict = {
            "name": device_properties.name,
            "major": device_properties.major,
            "minor": device_properties.minor,
            "total_memory": device_properties.total_memory,
            "total_memory_humanized": humanize.naturalsize(
                device_properties.total_memory,
                binary=True,
            ),
            "multi_processor_count": device_properties.multi_processor_count,
        }
        metadata["device_properties"] = device_properties_dict
    except:
        traceback_print()
        print("Continuing despite the error ...", file=sys.stderr)

    return metadata


##
class TorchBenchmarker:
    def __init__(
        self,
        *,
        output_dict,
        device=None,
        measure_carbon_p=False,
        country_iso_code="USA",
        tracking_mode="machine",
        output_dir=None,
        output_file="emissions.csv",
        output_append_p=False,
    ):
        self.device = device
        self.metadata = output_dict

        self.measure_carbon_p = measure_carbon_p
        self.country_iso_code = country_iso_code
        self.tracking_mode = tracking_mode
        self.output_dir = output_dir
        self.output_file = output_file
        self.output_append_p = output_append_p

        # self.tracker = None
        # self.start_time = None
        # self.end_time = None
        # self.max_memory_allocated = None

    def __enter__(self):
        torch.cuda.reset_peak_memory_stats(device=self.device)

        if self.measure_carbon_p:
            self.tracker = OfflineEmissionsTracker(
                country_iso_code=self.country_iso_code,
                tracking_mode=self.tracking_mode,
                save_to_file=bool(self.output_dir),
                output_dir=self.output_dir,
                output_file=self.output_file,
            )
            self.tracker.start()

        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        device = self.device

        self.end_time = time.time()
        time_taken = self.end_time - self.start_time
        time_taken_humanized = humanize.precisedelta(time_taken)
        self.metadata["time_total"] = time_taken
        self.metadata["time_total_humanized"] = time_taken_humanized

        self.max_memory_allocated = torch.cuda.max_memory_allocated(device=self.device)
        max_memory_allocated_humanized = humanize.naturalsize(
            self.max_memory_allocated,
            binary=True,
        )
        self.metadata["max_memory_allocated"] = self.max_memory_allocated
        self.metadata["max_memory_allocated_humanized"] = max_memory_allocated_humanized
        self.metadata["memory_stats"] = torch.cuda.memory_stats_as_nested_dict(
            device=device
        )

        if self.measure_carbon_p:
            if not self.output_append_p:
                rm(f"{self.output_dir}/{self.output_file}")

            self.tracker.stop()

            ##: @notNeeded
            # h(tracker.flush)
            # tracker.flush()
            ##


##
def tensorify_scalars(argnums=(0,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Store the original types of the arguments specified by argnums
            original_types = {argnum: torch.is_tensor(args[argnum]) for argnum in argnums}

            # Convert those arguments to tensors if they're not already
            new_args = list(args)
            for argnum in argnums:
                if not original_types[argnum]:
                    new_args[argnum] = torch.tensor(args[argnum])

            # Call the original function
            result = func(*new_args, **kwargs)

            # If the original type of an argument was not a tensor, convert the result back to the same type
            for argnum in original_types.keys():
                if not original_types[argnum]:
                    return result.item()

            return result
        return wrapper
    return decorator
##
