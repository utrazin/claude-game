"""Deterministic polygon calculations; generated triangles are never topology."""

from __future__ import annotations

import math

EPSILON = 1e-9


def newell_normal(points):
    points=tuple(points)
    return tuple(sum((a[(axis+1)%3]-b[(axis+1)%3])*
                     (a[(axis+2)%3]+b[(axis+2)%3])
                     for a,b in zip(points,points[1:]+points[:1]))
                 for axis in range(3))


def project_polygon(points):
    points=tuple(points)
    normal=newell_normal(points)
    length=math.sqrt(sum(value*value for value in normal))
    if length<=EPSILON:
        raise ValueError("Degenerate polygon")
    drop=max(range(3),key=lambda axis:(abs(normal[axis]),-axis))
    axes=tuple(axis for axis in range(3) if axis!=drop)
    return tuple((point[axes[0]],point[axes[1]]) for point in points),normal


def temporary_triangle_indices(points):
    """Calculation-only decomposition; quads match Blockbench diagonal A-C."""
    points=tuple(points)
    if len(points)<3:
        raise ValueError("Polygon needs at least three calculation points")
    if len(points)==3:
        return ((0,1,2),)
    if len(points)==4:
        return ((0,1,2),(0,2,3))
    projected,_=project_polygon(points)
    from .polygon_math import validate_contour
    validate_contour(projected)
    remaining=list(range(len(points)))
    area=sum(projected[a][0]*projected[b][1]-projected[b][0]*projected[a][1]
             for a,b in zip(remaining,remaining[1:]+remaining[:1]))
    sign=1 if area>0 else -1
    def cross2(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def inside(point,a,b,c):
        values=(cross2(a,b,point),cross2(b,c,point),cross2(c,a,point))
        return all(value>=-EPSILON for value in values) or all(value<=EPSILON for value in values)
    result=[]
    while len(remaining)>3:
        for position,current in enumerate(remaining):
            previous,following=remaining[position-1],remaining[(position+1)%len(remaining)]
            a,b,c=projected[previous],projected[current],projected[following]
            if sign*cross2(a,b,c)<=EPSILON:
                continue
            if any(inside(projected[index],a,b,c)
                   for index in remaining if index not in (previous,current,following)):
                continue
            result.append((previous,current,following))
            del remaining[position]
            break
        else:
            raise ValueError("Polygon cannot be decomposed safely")
    result.append(tuple(remaining))
    return tuple(result)


def polygon_area(points):
    projected,_=project_polygon(points)
    return abs(sum(a[0]*b[1]-b[0]*a[1]
                   for a,b in zip(projected,projected[1:]+projected[:1])))/2

