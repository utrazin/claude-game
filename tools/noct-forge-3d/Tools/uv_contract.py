"""Shared face ownership contract; no inference or geometry changes."""

# Smoothing reads neighbors and each mipmap level doubles the reach; 4 px keeps
# islands apart through the first two levels.
LINEAR_MIN_PADDING = 4


def filter_padding_warning(texture_filter, data):
    """Warn when linear filtering can mix neighboring islands; never changes UVs."""
    padding = data.get('unhandled_root_fields', {}).get('model_as_code', {}).get(
        'uv_packing', {}).get('island_padding', 0)
    if texture_filter != 'linear' or padding >= LINEAR_MIN_PADDING:
        return None
    return (f'texture_filter linear with island_padding {padding} px: smoothing and mipmaps mix '
            f'neighboring islands at the edges; set island_padding >= {LINEAR_MIN_PADDING} in the UV recipe '
            f'(--island-padding {LINEAR_MIN_PADDING}) and save with edge_dilation equal to it')


def sharing_links(data):
    raw = data.get('unhandled_root_fields', {}).get('model_as_code', {}).get('uv_sharing', [])
    if not isinstance(raw, list):
        raise ValueError('uv_sharing must be a list')
    links = {}
    for link in raw:
        if not isinstance(link, dict):
            raise ValueError('Invalid UV sharing declaration')
        refs = []
        for key in ('target', 'source'):
            ref = link.get(key)
            if not isinstance(ref, (list, tuple)) or len(ref) != 2 or not all(isinstance(v, str) and v for v in ref):
                raise ValueError('UV sharing references must contain element and face names')
            refs.append(tuple(ref))
        target, source = refs
        if not isinstance(link.get('mirror', False), bool):
            raise ValueError('UV sharing mirror must be a boolean')
        if not isinstance(link.get('region', False), bool):
            raise ValueError('UV sharing region must be a boolean')
        if target == source or target in links:
            raise ValueError(f'Duplicate or self-referencing UV follower: {target}')
        links[target] = source
    if any(source in links for source in links.values()):
        raise ValueError('UV sharing chains and cycles are forbidden; reference the owner directly')
    return links


def mirrored_targets(data):
    """Followers declared with mirror=True show the owner's pixels reflected."""
    raw = data.get('unhandled_root_fields', {}).get('model_as_code', {}).get('uv_sharing', [])
    return {tuple(link['target']) for link in raw if link.get('mirror', False)}


def region_targets(data):
    """Followers of a ``flat`` UV rule (``region: true``): they show their owner's island, whatever their shape."""
    raw = data.get('unhandled_root_fields', {}).get('model_as_code', {}).get('uv_sharing', [])
    return {tuple(link['target']) for link in raw if isinstance(link, dict) and link.get('region', False)}


def local_layout(elem, face_name, uv_scale, require_integer_uvs=True):
    """Per-vertex pixel layout the packer gives a face before placement.

    Cube faces and rectangular meshes use corners (0,0) (w,0) (w,h) (0,h); cube
    corners are keyed by index because cube faces have no vertices.
    """
    from .uv_packer import BoxUVPacker, _geometry_dimension
    if elem.get('type', 'cube') == 'cube':
        w, h = face_sizes({'elements': [elem]}, uv_scale, require_integer_uvs)[elem['name'], face_name]
        return list(range(4)), {0: [0, 0], 1: [w, 0], 2: [w, h], 3: [0, h]}
    face = elem['faces'][face_name]
    order = list(face['vertices'])
    if not elem.get('model_as_code_mesh'):
        try:
            w, h = (_geometry_dimension(v, f"{elem['name']}/{face_name}") * uv_scale
                    for v in BoxUVPacker._mesh_face_size(elem, face))
            return order, dict(zip(order, ([0, 0], [w, 0], [w, h], [0, h])))
        except ValueError as error:
            if 'four-vertex' not in str(error) and 'not a planar rectangle' not in str(error):
                raise
    return order, BoxUVPacker._mesh_face_layout(elem, face, uv_scale, require_integer_uvs)[2]


def mirror_correspondence(elements, target, source, uv_scale, require_integer_uvs=True):
    """Map each follower vertex to the owner vertex whose pixel it reuses.

    The follower must equal the owner's layout reflected across its width or
    its height, with the vertex order reversed as a mirror reverses winding.
    """
    f_order, follower = local_layout(elements[target[0]], target[1], uv_scale, require_integer_uvs)
    o_order, owner = local_layout(elements[source[0]], source[1], uv_scale, require_integer_uvs)
    if len(f_order) != len(o_order):
        raise ValueError(f'UV sharing topology differs: {target} -> {source}')
    width = max(p[0] for p in owner.values()) + min(p[0] for p in owner.values())
    height = max(p[1] for p in owner.values()) + min(p[1] for p in owner.values())
    tolerance = 0 if require_integer_uvs else 1e-8
    count = len(f_order)
    for reflect in (lambda p: (width - p[0], p[1]), lambda p: (p[0], height - p[1])):
        for shift in range(count):
            mapping = {f_order[i]: o_order[(shift - i) % count] for i in range(count)}
            if all(abs(a - b) <= tolerance for key, owner_key in mapping.items()
                   for a, b in zip(follower[key], reflect(owner[owner_key]))):
                return mapping
    raise ValueError(f'UV mirror shape differs (follower is not a reflection of the owner): {target} -> {source}')


def face_sizes(data, uv_scale=1, require_integer_uvs=True):
    from .uv_packer import BoxUVPacker, _geometry_dimension
    sizes = {}
    names = set()
    for elem in data.get('elements', []):
        if elem.get('type', 'cube') not in {'cube', 'mesh'}:
            continue
        name = elem.get('name')
        if not name or name in names:
            raise ValueError(f'Missing or duplicate element name: {name}')
        names.add(name)
        if elem.get('type', 'cube') == 'cube':
            start, end = elem.get('from', []), elem.get('to', [])
            if len(start) != 3 or len(end) != 3:
                raise ValueError(f'{name}: invalid cube geometry')
            x, y, z = [_geometry_dimension(abs(b-a), name) * uv_scale for a, b in zip(start, end)]
            dims = dict(north=(x,y), south=(x,y), east=(z,y), west=(z,y), up=(x,z), down=(x,z))
        elif elem.get('type') == 'mesh':
            dims = {}
            for key, face in elem.get('faces', {}).items():
                if face.get('texture', False) is None:
                    continue
                if elem.get('model_as_code_mesh'):
                    w, h, _ = BoxUVPacker._mesh_face_layout(elem, face, uv_scale, require_integer_uvs)
                    dims[key] = (w, h)
                    continue
                try:
                    size = BoxUVPacker._mesh_face_size(elem, face)
                    dims[key] = tuple(_geometry_dimension(v, f'{name}/{key}') * uv_scale for v in size)
                except ValueError as error:
                    if 'four-vertex' not in str(error) and 'not a planar rectangle' not in str(error):
                        raise
                    w, h, _ = BoxUVPacker._mesh_face_layout(elem, face, uv_scale, require_integer_uvs)
                    dims[key] = (w, h)
        else:
            raise ValueError(f'{name}: unsupported element type')
        for key, size in dims.items():
            if elem.get('faces', {}).get(key, {}).get('texture', False) is not None:
                sizes[name, key] = size
    return sizes


def validate_sharing(data, uv_scale=None, require_integer_uvs=None, *, mirrors=None):
    """Return follower -> owner links; pass a dict as ``mirrors`` to receive
    each mirrored follower's vertex correspondence."""
    from .uv_packer import BoxUVPacker
    links = sharing_links(data)
    mirrored = mirrored_targets(data)
    regions = region_targets(data)
    if require_integer_uvs is None:
        require_integer_uvs = data.get('unhandled_root_fields', {}).get('model_as_code', {}).get('uv_packing', {}).get('require_integer_uvs', True)
    if links:
        if uv_scale is None:
            uv_scale = data.get('unhandled_root_fields', {}).get('model_as_code', {}).get(
                'uv_packing', {}).get('uv_scale', 1)
        sizes = face_sizes(data, uv_scale, require_integer_uvs)
        for target, source in links.items():
            if target not in sizes or source not in sizes:
                raise ValueError(f'Missing or disabled UV face: {target} -> {source}')
            if target in regions:
                continue
            if sizes[target] != sizes[source]:
                raise ValueError(f'UV sharing dimensions differ: {target} -> {source}')
            elements = {elem.get('name'): elem for elem in data.get('elements', [])}
            if target in mirrored:
                mapping = mirror_correspondence(elements, target, source, uv_scale, require_integer_uvs)
                if mirrors is not None:
                    mirrors[target] = mapping
                continue
            a = elements[target[0]].get('faces', {}).get(target[1], {}).get('vertices')
            b = elements[source[0]].get('faces', {}).get(source[1], {}).get('vertices')
            a_count, b_count = (len(a) if a is not None else 4), (len(b) if b is not None else 4)
            if a_count != b_count:
                raise ValueError(f'UV sharing topology differs: {target} -> {source}')
            if a is not None and b is not None:
                _, _, a_uv = BoxUVPacker._mesh_face_layout(elements[target[0]],
                                                            elements[target[0]]['faces'][target[1]], uv_scale, require_integer_uvs)
                _, _, b_uv = BoxUVPacker._mesh_face_layout(elements[source[0]],
                                                            elements[source[0]]['faces'][source[1]], uv_scale, require_integer_uvs)
                a_shape = [a_uv[key] for key in a]
                b_shape = [b_uv[key] for key in b]
                if any(abs(x-y) > (0 if require_integer_uvs else 1e-8)
                       for pa, pb in zip(a_shape, b_shape) for x,y in zip(pa,pb)):
                    raise ValueError(f'UV sharing vertex order or shape differs: {target} -> {source}')
    return links
