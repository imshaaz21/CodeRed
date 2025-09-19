interface WarningBannerProps {
  message: string | null;
}

const WarningBanner = ({ message }: WarningBannerProps) => {
  if (!message) {
    return null;
  }
  return <div className="warning-banner">{message}</div>;
};

export default WarningBanner;
