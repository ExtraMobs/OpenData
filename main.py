from ipfs.ipfs import IPFS


def main():
    IPFS.init()
    IPFS.close_daemon()
    # CNPJ.download()


if __name__ == "__main__":
    main()
