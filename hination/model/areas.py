"""Stable forecast-area registry for the 45 current Điện Biên communes.

Coordinates are representative points inside the committed OpenStreetMap
polygons (ODbL, relation IDs recorded below).  Legacy IDs are retained for the
nine previously modeled areas so existing clients do not lose continuity.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Area:
    id: str
    name: str
    administrative_code: str
    osm_relation_id: int
    lat: float
    lon: float


FORECAST_AREAS = {
    "commune_19537811": Area("commune_19537811", "Xã Sín Thầu", "", 19537811, 22.3958973, 102.2745720),
    "muong_nhe": Area("muong_nhe", "Xã Mường Nhé", "03160", 19537914, 22.2169654, 102.4203498),
    "commune_19537915": Area("commune_19537915", "Xã Mường Toong", "", 19537915, 22.1839144, 102.5818160),
    "commune_19537916": Area("commune_19537916", "Xã Nậm Kè", "", 19537916, 22.0619828, 102.5143555),
    "commune_19571184": Area("commune_19571184", "Xã Xa Dung", "", 19571184, 21.3182894, 103.2995758),
    "tuan_giao": Area("tuan_giao", "Xã Tuần Giáo", "03253", 19571185, 21.6307491, 103.4439122),
    "commune_19571186": Area("commune_19571186", "Xã Tủa Thàng", "", 19571186, 22.0324289, 103.4386917),
    "tua_chua": Area("tua_chua", "Xã Tủa Chùa", "03217", 19571187, 21.8221187, 103.3617164),
    "commune_19571188": Area("commune_19571188", "Xã Tìa Dình", "", 19571188, 21.1414586, 103.3380428),
    "commune_19571189": Area("commune_19571189", "Xã Thanh Yên", "", 19571189, 21.3060702, 102.9473232),
    "commune_19571190": Area("commune_19571190", "Xã Thanh Nưa", "", 19571190, 21.4215085, 102.9733819),
    "commune_19571191": Area("commune_19571191", "Xã Thanh An", "", 19571191, 21.3018221, 103.0464810),
    "commune_19571192": Area("commune_19571192", "Xã Sính Phình", "", 19571192, 21.9436694, 103.3270886),
    "commune_19571193": Area("commune_19571193", "Xã Sín Chải", "", 19571193, 22.0538305, 103.3480596),
    "nam_po": Area("nam_po", "Xã Si Pa Phìn", "03199", 19571194, 21.8098376, 102.9201731),
    "commune_19571195": Area("commune_19571195", "Xã Sáng Nhè", "", 19571195, 21.8465622, 103.4586649),
    "commune_19571196": Area("commune_19571196", "Xã Sam Mứn", "", 19571196, 21.2072347, 102.9486785),
    "commune_19571197": Area("commune_19571197", "Xã Quảng Lâm", "", 19571197, 21.9859511, 102.6031629),
    "commune_19571198": Area("commune_19571198", "Xã Quài Tở", "", 19571198, 21.5417485, 103.4569434),
    "commune_19571199": Area("commune_19571199", "Xã Pú Nhung", "", 19571199, 21.7226384, 103.4901395),
    "commune_19571200": Area("commune_19571200", "Xã Pu Nhi", "", 19571200, 21.3456912, 103.1344866),
    "commune_19571201": Area("commune_19571201", "Xã Phình Giàng", "", 19571201, 21.1251928, 103.2244561),
    "commune_19571202": Area("commune_19571202", "Xã Pa Ham", "", 19571202, 21.8913284, 103.2239097),
    "commune_19571203": Area("commune_19571203", "Xã Núa Ngam", "", 19571203, 21.1792549, 103.0525592),
    "commune_19571204": Area("commune_19571204", "Xã Nậm Nèn", "", 19571204, 21.8044040, 103.2258203),
    "commune_19571205": Area("commune_19571205", "Xã Nà Tấu", "", 19571205, 21.5624221, 103.1443005),
    "dien_bien_dong": Area("dien_bien_dong", "Xã Na Son", "03203", 19571206, 21.2972456, 103.2143726),
    "commune_19571207": Area("commune_19571207", "Xã Na Sang", "", 19571207, 21.7755238, 103.0614101),
    "commune_19571208": Area("commune_19571208", "Xã Nà Hỳ", "", 19571208, 21.8333380, 102.7325616),
    "commune_19571209": Area("commune_19571209", "Xã Nà Bủng", "", 19571209, 21.7258132, 102.7160411),
    "commune_19571210": Area("commune_19571210", "Xã Mường Tùng", "", 19571210, 21.9519678, 103.0926433),
    "commune_19571211": Area("commune_19571211", "Phường Mường Thanh", "", 19571211, 21.3662597, 103.0342256),
    "commune_19571212": Area("commune_19571212", "Xã Mường Pồn", "", 19571212, 21.5869655, 103.0296833),
    "commune_19571213": Area("commune_19571213", "Xã Mường Phăng", "", 19571213, 21.4726893, 103.1044667),
    "commune_19571214": Area("commune_19571214", "Xã Mường Nhà", "", 19571214, 21.0277314, 103.1676378),
    "commune_19571215": Area("commune_19571215", "Xã Mường Mùn", "", 19571215, 21.7248422, 103.3184198),
    "commune_19571216": Area("commune_19571216", "Xã Mường Luân", "", 19571216, 21.2469241, 103.3801762),
    "muong_lay": Area("muong_lay", "Phường Mường Lay", "03151", 19571217, 22.0160376, 103.1782851),
    "commune_19571218": Area("commune_19571218", "Xã Mường Lạn", "", 19571218, 21.4514939, 103.3176827),
    "muong_cha": Area("muong_cha", "Xã Mường Chà", "03166", 19571219, 21.9786223, 102.7777717),
    "muong_ang": Area("muong_ang", "Xã Mường Ảng", "03256", 19571220, 21.4888505, 103.2218525),
    "dien_bien_phu": Area("dien_bien_phu", "Phường Điện Biên Phủ", "03127", 19571221, 21.4140962, 103.0576943),
    "commune_19571222": Area("commune_19571222", "Xã Chiềng Sinh", "", 19571222, 21.6100291, 103.3363912),
    "commune_19571223": Area("commune_19571223", "Xã Chà Tở", "", 19571223, 21.9896598, 102.9376092),
    "commune_19571224": Area("commune_19571224", "Xã Búng Lao", "", 19571224, 21.5463225, 103.2891237),
}


AREA_IDS = tuple(FORECAST_AREAS)
