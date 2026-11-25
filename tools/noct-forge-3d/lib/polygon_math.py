"""Planar contour predicates shared by construction and normalization."""
import math

def _cross2(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def validate_contour(points):
    if len(points)<3 or len(set(points)) != len(points): raise ValueError('Profile needs distinct points')
    if any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points): raise ValueError('Invalid profile coordinates')
    area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))
    if abs(area)<1e-10: raise ValueError('Degenerate profile')
    n=len(points)
    def on(a,b,p):
        return abs(_cross2(a,b,p))<1e-10 and all(min(a[i],b[i])-1e-10<=p[i]<=max(a[i],b[i])+1e-10 for i in (0,1))
    for i in range(n):
        a,b=points[i],points[(i+1)%n]
        if math.dist(a,b)<1e-10: raise ValueError('Zero-length profile edge')
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1): continue
            c,d=points[j],points[(j+1)%n]
            if (_cross2(a,b,c)*_cross2(a,b,d)<0 and _cross2(c,d,a)*_cross2(c,d,b)<0) or any((on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b))):
                raise ValueError('Self-intersecting profile')
    return area
