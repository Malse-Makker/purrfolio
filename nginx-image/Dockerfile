# nginx:alpine, met de Alpine-pakketten bijgewerkt.
#
# Het officiële image wordt pas opnieuw gebouwd bij een nieuwe nginx- of
# Alpine-versie. Een lek in een losse bibliotheek (brotli, oktober 2026) bleef
# daardoor weken in het image zitten terwijl Alpine de fix al had. Met
# apk upgrade komt die fix er bij de eerstvolgende build in. onderhoud.py op
# OVH bouwt zonder cache zodra de dagelijkse scan hier een kritiek lek ziet;
# anders bleef deze laag gecachet en veranderde er niets.
FROM nginx:alpine
RUN apk upgrade --no-cache
