nom=""
while nom=="":
    nom = input("Entrez un nom : ")

prenom= ""
while prenom=="":
    prenom = input("Entrez un prenom : ")

nom =""
email= "Votre email est " + nom.lower() + prenom.lower().replace(" ","") +"@gmail.com"
