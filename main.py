import general.zip
from brazil.cnpj.cnpj import CNPJ
from ipfs.ipfs import IPFS


def main():
    IPFS.init()
    CNPJ.process()
    IPFS.close_daemon()


if __name__ == "__main__":
    main()
