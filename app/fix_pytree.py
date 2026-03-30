"""
Workaround for torch.utils._pytree compatibility issue
This patches the issue before importing sentence_transformers
"""
import torch.utils._pytree as pytree

# Add the missing function if it doesn't exist
if not hasattr(pytree, 'register_pytree_node'):
    def register_pytree_node(cls, flatten_fn, unflatten_fn, **kwargs):
        """Dummy implementation for compatibility"""
        # Accept any keyword arguments (like serialized_type_name) but do nothing
        pass
    
    pytree.register_pytree_node = register_pytree_node
