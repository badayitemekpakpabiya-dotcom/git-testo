from index import nom,prenom
resultz= nom.upper()
print(resultz+", merci de choisir notre site pour votre identification ")
#demander s'il ou elle est marié(e)
marie=input("Ête-vous marié(e) ?"+" OUI ou NON ?").upper()

if marie=="OUI":
    marie1=input("Quel est le nom de votre conjoint ou conjointe ? ")
    marie2=input("Quel est son prénom ? ")
    print("Indentité du cojoint ou conjointe :\n Madame ou Monsieur: "+marie1.upper() +" " + marie2.title() )
if marie=="NON":
    print("Ok donc vous ête célibataire, Monsieur "+prenom.title())


print("Merci de votre identification .\n Nous somme très content que vous ayez choisi notre plateforme pour votre identification ")

#demander le metier de la personne
profession = input("Executer-vous un métier ?" + " OUI ou NON ?").upper()

if profession=="OUI":
    profession1=input("Ête-vous un salarier ? "+ " OUI ou NON ?" ).upper()
    if profession1=="OUI":
        profession1_2=input("Quel est le nom de votre métier ? ")
    if profession1=="NON":
        profession1_3=input("Quel est le nom de votre métier ? ")
if profession=="NON":
    print("OK")

