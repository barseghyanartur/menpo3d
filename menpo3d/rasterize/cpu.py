import numpy as np
from menpo.transform.piecewiseaffine.base import barycentric_vectors
from menpo.image import BooleanImage, MaskedImage


def _pixels_to_check_python():
    pixel_locations = []
    tri_indices = []

    for i, ((s_x, s_y), (e_x, e_y)) in enumerate(zip(start, end)):
        for x in range(s_x, e_x):
            for y in range(s_y, e_y):
                pixel_locations.append((x, y))
                tri_indices.append(i)

    pixel_locations = np.array(pixel_locations)
    tri_indices = np.array(tri_indices)
    return pixel_locations, tri_indices


def _pixels_to_check_alt_python():
    pixel_locations = []
    tri_indices = []

    for i, ((s_x, s_y), (e_x, e_y)) in enumerate(zip(start, end)):
        x = np.arange(s_x, e_x)
        y = np.arange(s_y, e_y)
        grid = np.transpose([np.tile(x, len(y)), np.repeat(y, len(x))])
        pixel_locations.append(grid)
        tri_indices.append(np.repeat(i, grid.shape[0]))

    pixel_locations = np.array(pixel_locations)
    tri_indices = np.array(tri_indices)
    return pixel_locations, tri_indices


try:
    from .tripixel import pixels_to_check
except IOError:
    print('Falling back to CPU pixel checking')
    pixels_to_check = _pixels_to_check_python


def pixel_locations_and_tri_indices(mesh):
    vertex_trilist = mesh.points[mesh.trilist]
    start = np.floor(vertex_trilist.min(axis=1)[:, :2]).astype(int)
    end = np.ceil(vertex_trilist.max(axis=1)[:, :2]).astype(int)
    n_sites = np.product((end - start), axis=1).sum()
    return pixels_to_check(start, end, n_sites)


def alpha_beta(i, ij, ik, points):
    ip = points - i
    dot_jj = np.einsum('dt, dt -> t', ij, ij)
    dot_kk = np.einsum('dt, dt -> t', ik, ik)
    dot_jk = np.einsum('dt, dt -> t', ij, ik)
    dot_pj = np.einsum('dt, dt -> t', ip, ij)
    dot_pk = np.einsum('dt, dt -> t', ip, ik)

    d = 1.0/(dot_jj * dot_kk - dot_jk * dot_jk)
    alpha = (dot_kk * dot_pj - dot_jk * dot_pk) * d
    beta = (dot_jj * dot_pk - dot_jk * dot_pj) * d
    return alpha, beta


def xy_bcoords(mesh, tri_indices, pixel_locations):
    i, ij, ik = barycentric_vectors(mesh.points[:, :2], mesh.trilist)
    i = i[:, tri_indices]
    ij = ij[:, tri_indices]
    ik = ik[:, tri_indices]
    a, b = alpha_beta(i, ij, ik, pixel_locations.T)
    c = 1 - a - b
    bcoords = np.array([a, b, c]).T
    return bcoords


def tri_containment(bcoords):
    alpha, beta, _ = bcoords.T
    return np.logical_and(np.logical_and(
        alpha >= 0, beta >= 0),
        alpha + beta <= 1)


def z_values_for_bcoords(mesh, bcoords, tri_indices):
    return mesh.barycentric_coordinate_interpolation(
        mesh.points[:, -1][..., None], bcoords, tri_indices)[:, 0]


def barycentric_coordinate_image(mesh, width, height):

    xy, tri_indices = pixel_locations_and_tri_indices(mesh)

    bcoords = xy_bcoords(mesh, tri_indices, xy)

    # check the mask based on triangle containment
    in_tri_mask = tri_containment(bcoords)

    # use this mask on the pixels
    xy = xy[in_tri_mask]
    bcoords = bcoords[in_tri_mask]
    tri_indices = tri_indices[in_tri_mask]

    # Find the z values for all pixels and calculate the mask
    z_values = z_values_for_bcoords(mesh, bcoords, tri_indices)

    # argsort z from smallest to biggest - use this to sort all data
    sort = np.argsort(z_values)
    xy = xy[sort]
    bcoords = bcoords[sort]
    tri_indices = tri_indices[sort]

    # make a unique id per-pixel location
    pixel_index = xy[:, 0] * width + xy[:, 1]
    # find the first instance of each pixel site by depth
    _, z_buffer_mask = np.unique(pixel_index, return_index=True)

    # mask the locations again
    xy = xy[z_buffer_mask]
    bcoords = bcoords[z_buffer_mask]
    tri_indices = tri_indices[z_buffer_mask]

    tri_index_img = np.zeros((1, height, width))
    bcoord_img = np.zeros((3, height, width))
    mask = np.zeros((height, width), dtype=np.bool)
    mask[height - xy[:, 1], xy[:, 0]] = True
    tri_index_img[:, height - xy[:, 1], xy[:, 0]] = tri_indices
    bcoord_img[:, height - xy[:, 1], xy[:, 0]] = bcoords.T

    mask = BooleanImage(mask)
    return (MaskedImage(tri_index_img, mask=mask.copy(), copy=False),
            MaskedImage(bcoord_img, mask=mask.copy(), copy=False))
