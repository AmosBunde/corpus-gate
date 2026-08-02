FROM node:22-alpine

WORKDIR /app

COPY ui/package.json ./
RUN npm install --no-audit --no-fund

COPY ui/ .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "--port", "3000"]
